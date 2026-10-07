from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from .auction import normalize_auction
from .config import Settings
from .fiscal import AUCTIONS_URL, FiscalDataClient
from .http_client import TreasuryHttpClient
from .raw_store import RawStore
from .repository import Repository
from .validation import validate_auction


LOG = logging.getLogger(__name__)
@dataclass
class RunOutcome:
    status: str
    received: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    pages_attempted: int = 0
    pages_succeeded: int = 0
    error_summary: str | None = None

    @property
    def exit_code(self) -> int:
        return {"SUCCESS": 0, "DRY_RUN": 0, "PARTIAL_FAILURE": 3, "FAILED": 1}.get(self.status, 1)


class Pipeline:
    def __init__(self, settings: Settings, repository: Repository | None, dry_run: bool = False) -> None:
        self.settings = settings
        self.repository = repository
        self.dry_run = dry_run
        self.raw_store = RawStore(settings.raw_root)

    def auctions(self, start: date, end: date, job_type: str) -> RunOutcome:
        run_id = self._start("FISCAL_DATA_AUCTIONS", job_type, start, end)
        outcome = RunOutcome("DRY_RUN" if self.dry_run else "SUCCESS")
        failures: list[str] = []
        with TreasuryHttpClient(
            self.settings.user_agent, self.settings.http_timeout_seconds, self.settings.http_max_retries,
            self.settings.http_backoff_base_seconds,
            ca_bundle=str(self.settings.ca_bundle) if self.settings.ca_bundle else None,
            allowed_hosts={'api.fiscaldata.treasury.gov'},
        ) as http:
            try:
                for page in FiscalDataClient(http, self.settings.auction_page_size).iter_auction_pages(start, end):
                    outcome.pages_attempted += 1
                    outcome.received += len(page.rows)
                    snapshot_id: UUID | None = None
                    if not self.dry_run:
                        stored = self.raw_store.put(page.raw_bytes, "fiscal-auctions", page.response_headers.get("content-type"))
                        snapshot_id = self.repository.save_snapshot(
                            run_id, "FISCAL_DATA_AUCTIONS", page.request_url, stored, page.response_headers, meta=page.meta
                        )
                    for raw in page.rows:
                        try:
                            record = normalize_auction(raw)
                            issues = validate_auction(record)
                            if any(issue.severity == "ERROR" for issue in issues):
                                outcome.rejected += 1
                                failures.append(f"page {page.page_number}: validation rejected {record.business_key}")
                                if not self.dry_run:
                                    for issue in issues:
                                        self.repository.issue(run_id, issue.rule, issue.message, severity=issue.severity,
                                                              snapshot_id=snapshot_id, field_name=issue.field)
                                continue
                            if not self.dry_run:
                                event_id, action = self.repository.upsert_auction(record, raw, snapshot_id)
                                for issue in issues:
                                    self.repository.issue(
                                        run_id, issue.rule, issue.message, severity=issue.severity, snapshot_id=snapshot_id,
                                        entity_type="auction_event", entity_id=event_id, field_name=issue.field,
                                    )
                            else:
                                action = "UNCHANGED"
                            if action == "INSERTED":
                                outcome.inserted += 1
                            elif action == "UPDATED":
                                outcome.updated += 1
                            else:
                                outcome.unchanged += 1
                        except Exception as exc:
                            outcome.rejected += 1
                            failures.append(f"page {page.page_number}: {exc}")
                            LOG.exception("auction row rejected", extra={"page": page.page_number})
                            if not self.dry_run:
                                self.repository.issue(run_id, "AUCTION_NORMALIZATION", str(exc), snapshot_id=snapshot_id)
                    outcome.pages_succeeded += 1
                    self._checkpoint(run_id, outcome, {"last_completed_page": page.page_number, "total_pages": page.meta.get("total-pages")})
            except Exception as exc:
                outcome.pages_attempted = max(outcome.pages_attempted, outcome.pages_succeeded + 1)
                failures.append(str(exc))
                if not self.dry_run:
                    self.repository.record_request(run_id, AUCTIONS_URL, error=str(exc))
                    self.repository.issue(run_id, "AUCTION_PAGE_FAILED", str(exc))
                LOG.exception("auction page failed")
        if failures:
            outcome.status = "PARTIAL_FAILURE" if outcome.pages_succeeded else "FAILED"
            outcome.error_summary = " | ".join(failures[:10])
        self._finish(run_id, outcome)
        return outcome

    def sync_auctions(self, today: date | None = None) -> RunOutcome:
        today = today or datetime.now(UTC).date()
        return self.auctions(today - timedelta(days=self.settings.auction_overlap_days), today + timedelta(days=45), "SYNC_AUCTIONS")

    def _start(self, source: str, job_type: str, start: date | None = None, end: date | None = None) -> UUID | None:
        return None if self.dry_run else self.repository.start_run(source, job_type, start, end)

    def _checkpoint(self, run_id: UUID | None, outcome: RunOutcome, checkpoint: dict[str, object]) -> None:
        if run_id:
            self.repository.update_run(run_id, pages_attempted=outcome.pages_attempted, pages_succeeded=outcome.pages_succeeded,
                                       rows_received=outcome.received, rows_inserted=outcome.inserted, rows_updated=outcome.updated,
                                       rows_unchanged=outcome.unchanged, rows_rejected=outcome.rejected, checkpoint=checkpoint)

    def _finish(self, run_id: UUID | None, outcome: RunOutcome) -> None:
        if run_id:
            self.repository.update_run(run_id, status=outcome.status, finished_at=datetime.now(UTC),
                                       pages_attempted=outcome.pages_attempted, pages_succeeded=outcome.pages_succeeded,
                                       rows_received=outcome.received, rows_inserted=outcome.inserted, rows_updated=outcome.updated,
                                       rows_unchanged=outcome.unchanged, rows_rejected=outcome.rejected, error_summary=outcome.error_summary)
