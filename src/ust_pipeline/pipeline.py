from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Iterable
from uuid import UUID

from .auction import normalize_auction
from .config import Settings
from .fiscal import AUCTIONS_URL, FiscalDataClient
from .http_client import TreasuryHttpClient
from .qra.discovery import QraLink, discover_qra_index
from .qra.parsers import ParserDispatcher
from .raw_store import RawStore
from .repository import Repository
from .validation import validate_auction


LOG = logging.getLogger(__name__)
QRA_SEED_URL = "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/most-recent-quarterly-refunding-documents"
QRA_ARCHIVE_URL = "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/quarterly-refunding-archives/"
QRA_SURVEY_ARCHIVE_URL = "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/quarterly-refunding-archives/primary-dealer-auction-size-survey"


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
    documents_attempted: int = 0
    documents_succeeded: int = 0
    documents_review_required: int = 0
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

    def crawl_qra(self, *, latest: bool = True, backfill_from: int | None = None) -> RunOutcome:
        run_id = self._start("QRA", "CRAWL_QRA")
        outcome = RunOutcome("DRY_RUN" if self.dry_run else "SUCCESS")
        failures: list[str] = []
        index_next_dates: list[date] = []
        with TreasuryHttpClient(
            self.settings.user_agent, self.settings.http_timeout_seconds, self.settings.http_max_retries,
            self.settings.http_backoff_base_seconds,
            ca_bundle=str(self.settings.ca_bundle) if self.settings.ca_bundle else None,
            allowed_hosts={'home.treasury.gov'},
        ) as http:
            page_urls = [QRA_SEED_URL, QRA_SURVEY_ARCHIVE_URL] if latest else [QRA_SEED_URL, QRA_ARCHIVE_URL, QRA_SURVEY_ARCHIVE_URL]
            document_links: dict[str, QraLink] = {}
            visited_pages: set[str] = set()
            for page_url in page_urls:
                outcome.documents_attempted += 1
                try:
                    response = http.get(page_url)
                    visited_pages.add(page_url)
                    index = discover_qra_index(response.content, page_url)
                    index_next_dates.extend(index.next_release_dates)
                    for link in index.links:
                        if latest and page_url == QRA_SURVEY_ARCHIVE_URL and link.document_type == "PRIMARY_DEALER_SURVEY_PDF":
                            if any(x.document_type == "PRIMARY_DEALER_SURVEY_PDF" for x in document_links.values()):
                                continue
                        if backfill_from and link.document_type not in {"QRA_ARCHIVE_HTML", "PRIMARY_DEALER_SURVEY_ARCHIVE_HTML"} and (not link.refunding_year or link.refunding_year < backfill_from):
                            continue
                        if latest and link.document_type in {"QRA_ARCHIVE_HTML", "PRIMARY_DEALER_SURVEY_ARCHIVE_HTML"}:
                            continue
                        document_links.setdefault(link.url, link)
                    if not self.dry_run:
                        stored = self.raw_store.put(response.content, "qra", response.headers.get("content-type"))
                        self.repository.save_snapshot(run_id, "QRA", page_url, stored, dict(response.headers), final_url=str(response.url))
                    outcome.documents_succeeded += 1
                except Exception as exc:
                    failures.append(f"{page_url}: {exc}")
                    outcome.rejected += 1
                    if not self.dry_run:
                        self.repository.record_request(run_id, page_url, error=str(exc))
                        self.repository.issue(run_id, "QRA_INDEX_FAILED", str(exc))
                    LOG.exception("QRA index failed", extra={"url": page_url})
                if self.settings.qra_request_delay_seconds:
                    time.sleep(self.settings.qra_request_delay_seconds)

            if not latest:
                archive_pages = [link for link in document_links.values() if link.document_type in {"QRA_ARCHIVE_HTML", "PRIMARY_DEALER_SURVEY_ARCHIVE_HTML"}]
                for archive in archive_pages:
                    if archive.url in visited_pages:
                        continue
                    try:
                        outcome.documents_attempted += 1
                        response = http.get(archive.url)
                        for link in discover_qra_index(response.content, archive.url).links:
                            if not backfill_from or (link.refunding_year and link.refunding_year >= backfill_from):
                                document_links.setdefault(link.url, link)
                        visited_pages.add(archive.url)
                        if not self.dry_run:
                            stored = self.raw_store.put(response.content, "qra", response.headers.get("content-type"))
                            self.repository.save_snapshot(run_id, "QRA", archive.url, stored, dict(response.headers), final_url=str(response.url))
                        outcome.documents_succeeded += 1
                    except Exception as exc:
                        failures.append(f"{archive.url}: {exc}")
                        outcome.rejected += 1
                        if not self.dry_run:
                            self.repository.record_request(run_id, archive.url, error=str(exc))
                            self.repository.issue(run_id, "QRA_ARCHIVE_INDEX_FAILED", str(exc))
                        LOG.exception("QRA archive index failed", extra={"url": archive.url})
                    if self.settings.qra_request_delay_seconds:
                        time.sleep(self.settings.qra_request_delay_seconds)

            documents = [link for link in document_links.values() if link.document_type not in {"QRA_ARCHIVE_HTML", "PRIMARY_DEALER_SURVEY_ARCHIVE_HTML"}]
            for link in documents:
                outcome.documents_attempted += 1
                snapshot_id = None
                try:
                    etag = modified = None
                    if not self.dry_run:
                        etag, modified = self.repository.conditional_headers(link.url)
                    response = http.get(link.url, etag=etag, last_modified=modified)
                    if response.status_code == 304:
                        if not self.dry_run:
                            self.repository.record_request(run_id, link.url, 304, dict(response.headers))
                        outcome.unchanged += 1
                        outcome.documents_succeeded += 1
                        continue
                    snapshot_id = None
                    if not self.dry_run:
                        stored = self.raw_store.put(response.content, "qra", response.headers.get("content-type"))
                        snapshot_id = self.repository.save_snapshot(run_id, "QRA", link.url, stored, dict(response.headers), link=link, final_url=str(response.url))
                    parsed = ParserDispatcher.parse(link.document_type, response.content)
                    if parsed.status in {"QUARANTINED", "REVIEW_REQUIRED", "FAILED"}:
                        outcome.documents_review_required += 1
                    outcome.received += len(parsed.records)
                    if not self.dry_run:
                        year, quarter = self._year_quarter(link, documents)
                        month = {1: 2, 2: 5, 3: 8, 4: 11}[quarter]
                        policy = next((d for d in documents if d.document_type == "POLICY_STATEMENT_HTML" and self._year_quarter(d, documents) == (year, quarter)), None)
                        release = policy.release_datetime if policy else None
                        # Main refunding statement is the Wednesday release; agenda and financing releases remain document-level.
                        next_release = next((d for d in sorted(index_next_dates) if d.weekday() == 2 and d > (release.date() if release else date(year, month, 1))), None) if release else None
                        qra_id = self.repository.upsert_refunding(year, month, QRA_SEED_URL, release, next_release)
                        _, _, action = self.repository.save_qra_document(qra_id, link, snapshot_id, stored.sha256, parsed)
                        if action == "INSERTED":
                            outcome.inserted += 1
                        elif action == "UPDATED":
                            outcome.updated += 1
                        else:
                            outcome.unchanged += 1
                        for issue in parsed.issues:
                            self.repository.issue(run_id, issue.rule, issue.message, severity=issue.severity, snapshot_id=snapshot_id)
                    outcome.documents_succeeded += 1
                except Exception as exc:
                    failures.append(f"{link.url}: {exc}")
                    outcome.rejected += 1
                    if not self.dry_run:
                        self.repository.record_request(run_id, link.url, error=str(exc))
                        self.repository.issue(run_id, "QRA_DOCUMENT_FAILED", str(exc), snapshot_id=snapshot_id)
                    LOG.exception("QRA document failed", extra={"url": link.url})
                if self.settings.qra_request_delay_seconds:
                    time.sleep(self.settings.qra_request_delay_seconds)
        if failures:
            outcome.status = "PARTIAL_FAILURE" if outcome.documents_succeeded else "FAILED"
            outcome.error_summary = " | ".join(failures[:10])
        self._finish(run_id, outcome)
        return outcome

    @staticmethod
    def _year_quarter(link: QraLink, links: Iterable[QraLink]) -> tuple[int, int]:
        if link.refunding_year and link.refunding_quarter:
            return link.refunding_year, link.refunding_quarter
        if link.release_datetime:
            return link.release_datetime.year, (link.release_datetime.month - 1) // 3 + 1
        raise ValueError(f"QRA release period could not be proven: {link.url}")

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
                                       documents_attempted=outcome.documents_attempted, documents_succeeded=outcome.documents_succeeded,
                                       documents_review_required=outcome.documents_review_required,
                                       rows_received=outcome.received, rows_inserted=outcome.inserted, rows_updated=outcome.updated,
                                       rows_unchanged=outcome.unchanged, rows_rejected=outcome.rejected, error_summary=outcome.error_summary)
