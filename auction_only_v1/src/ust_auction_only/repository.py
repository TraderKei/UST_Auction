from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

from .auction import AuctionRecord, parse_yes_no
from .raw_store import StoredRaw


AUCTION_PARSER_VERSION = "auction-normalizer-1.1.0"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _insert(connection: Connection, table: str, values: dict[str, Any], json_columns: set[str] | None = None) -> None:
    json_columns = json_columns or set()
    columns = list(values)
    expressions = [f"CAST(:{column} AS jsonb)" if column in json_columns else f":{column}" for column in columns]
    payload = {key: json_text(value) if key in json_columns else value for key, value in values.items()}
    connection.execute(text(f"INSERT INTO ust.{table} ({','.join(columns)}) VALUES ({','.join(expressions)})"), payload)


def _upsert_child(connection: Connection, table: str, values: dict[str, Any], key: str) -> None:
    columns = list(values)
    updates = ",".join(f"{column}=EXCLUDED.{column}" for column in columns if column != key)
    connection.execute(
        text(f"INSERT INTO ust.{table} ({','.join(columns)}) VALUES ({','.join(':'+column for column in columns)}) "
             f"ON CONFLICT ({key}) DO UPDATE SET {updates}"),
        values,
    )


class Repository:
    def __init__(self, database_url: str | None = None, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True, hide_parameters=True)

    @contextmanager
    def job_lock(self):
        with self.engine.connect() as connection:
            acquired = connection.execute(text("SELECT pg_try_advisory_lock(hashtext('ust_pipeline_ingestion'))")).scalar_one()
            if not acquired:
                raise RuntimeError("another UST ingestion command is running")
            try:
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(hashtext('ust_pipeline_ingestion'))"))

    def init_schema(self, ddl_path: Path) -> None:
        with self.engine.begin() as connection:
            connection.exec_driver_sql(ddl_path.read_text(encoding="utf-8"), execution_options={"no_parameters": True})

    def start_run(self, source_name: str, job_type: str, start: date | None = None, end: date | None = None) -> UUID:
        run_id = uuid4()
        with self.engine.begin() as connection:
            _insert(connection, "ingestion_run", {
                "run_id": run_id, "source_name": source_name, "job_type": job_type,
                "requested_from": start, "requested_to": end,
            })
        return run_id

    def update_run(self, run_id: UUID, **values: Any) -> None:
        allowed = {
            "status", "finished_at", "pages_attempted", "pages_succeeded", "rows_received", "rows_inserted", "rows_updated", "rows_unchanged", "rows_rejected", "checkpoint", "error_summary",
        }
        if not set(values).issubset(allowed):
            raise ValueError("unknown ingestion_run field")
        assignments = [f"{key}=CAST(:{key} AS jsonb)" if key == "checkpoint" else f"{key}=:{key}" for key in values]
        payload = {key: json_text(value) if key == "checkpoint" else value for key, value in values.items()}
        payload["run_id"] = run_id
        with self.engine.begin() as connection:
            connection.execute(text(f"UPDATE ust.ingestion_run SET {','.join(assignments)} WHERE run_id=:run_id"), payload)

    def save_snapshot(
        self, run_id: UUID, source: str, url: str, raw: StoredRaw, headers: dict[str, str], *,
        fetched_at: datetime | None = None, meta: dict[str, Any] | None = None,
        http_status: int = 200, final_url: str | None = None,
    ) -> UUID:
        fetched_at = fetched_at or datetime.now(UTC)
        with self.engine.begin() as connection:
            request_id = connection.execute(text(
                "INSERT INTO ust.source_request(run_id,request_url,safe_parameters,http_status,response_headers,fetched_at) "
                "VALUES(:run_id,:url,CAST(:params AS jsonb),:status,CAST(:headers AS jsonb),:fetched_at) RETURNING source_request_id"
            ), {"run_id": run_id, "url": url,
                "params": json_text({key: value for key, value in parse_qsl(urlsplit(url).query) if key in {"fields", "filter", "sort", "format", "page[number]", "page[size]"}}),
                "status": http_status, "headers": json_text(headers), "fetched_at": fetched_at}).scalar_one()
            existing = connection.execute(text(
                "SELECT source_snapshot_id FROM ust.source_snapshot WHERE source_url=:url AND content_sha256=:hash"
            ), {"url": url, "hash": raw.sha256}).scalar_one_or_none()
            if existing:
                return existing
            snapshot_id = uuid4()
            _insert(connection, "source_snapshot", {
                "source_snapshot_id": snapshot_id, "source_request_id": request_id, "source_name": source,
                "source_url": url, "final_url": final_url or url, "content_sha256": raw.sha256,
                "mime_type": headers.get("content-type", "application/octet-stream"), "content_length": raw.size_bytes,
                "etag": headers.get("etag"), "last_modified": headers.get("last-modified"), "fetched_at": fetched_at,
                "raw_storage_uri": str(raw.path.resolve()), "parser_version": AUCTION_PARSER_VERSION,
                "response_meta": meta or {},
            }, {"response_meta"})
            return snapshot_id

    def record_request(self, run_id, url, status=None, headers=None, error=None):
        with self.engine.begin() as connection:
            _insert(connection, "source_request", {"run_id": run_id,"request_url": url,"http_status": status,
                    "response_headers": headers or {},"error_message": error}, {"response_headers"})

    def issue(self, run_id: UUID, rule: str, message: str, *, severity: str = "ERROR", snapshot_id: UUID | None = None,
              entity_type: str | None = None, entity_id: UUID | None = None, field_name: str | None = None,
              raw_value: Any = None, null_reason: str | None = None) -> None:
        with self.engine.begin() as connection:
            _insert(connection, "data_quality_issue", {
                "run_id": run_id, "source_snapshot_id": snapshot_id, "entity_type": entity_type, "entity_id": entity_id,
                "field_name": field_name, "severity": severity, "rule_code": rule, "raw_value": None if raw_value is None else str(raw_value),
                "null_reason": null_reason, "message": message,
            })

    def upsert_auction(self, record: AuctionRecord, raw_record: dict[str, Any], snapshot_id: UUID | None) -> tuple[UUID, str]:
        content_hash = record.canonical_hash()
        with self.engine.begin() as connection:
            security_id = connection.execute(text(
                "INSERT INTO ust.security_master(cusip,security_type,original_security_term,series,inflation_index_security,floating_rate,original_issue_date,maturity_date) "
                "VALUES(:cusip,:security_type,:original_security_term,:series,:inflation_index_security,:floating_rate,:original_issue_date,:maturity_date) "
                "ON CONFLICT(cusip) DO UPDATE SET last_seen_at=clock_timestamp(),security_type=EXCLUDED.security_type,"
                "original_security_term=EXCLUDED.original_security_term,maturity_date=EXCLUDED.maturity_date RETURNING security_id"
            ), {key: getattr(record, key) for key in ("cusip", "security_type", "original_security_term", "series", "inflation_index_security", "floating_rate", "original_issue_date", "maturity_date")}).scalar_one()
            existing = connection.execute(text(
                "SELECT auction_event_id,current_content_hash FROM ust.auction_event WHERE business_key_hash=:key FOR UPDATE"
            ), {"key": record.business_key_hash}).first()
            event_id = existing[0] if existing else uuid4()
            if existing and existing[1].strip() == content_hash:
                connection.execute(text("UPDATE ust.auction_event SET last_seen_at=clock_timestamp() WHERE auction_event_id=:id"), {"id": event_id})
                self._lineage(connection, event_id, snapshot_id)
                return event_id, "UNCHANGED"
            event_values = {
                "auction_event_id": event_id, "security_id": security_id, "cusip": record.cusip, "record_date": record.record_date,
                "announcement_date": record.announcemt_date, "auction_date": record.auction_date, "issue_date": record.issue_date,
                "maturity_date": record.maturity_date, "security_type": record.security_type, "source_security_type": record.source_security_type,
                "security_term": record.security_term,
                "normalized_security_term": record.normalized_security_term, "security_term_day_month": record.security_term_day_month,
                "security_term_week_year": record.security_term_week_year, "auction_format": record.auction_format,
                "reopening": record.reopening, "cash_management_bill": record.cash_management_bill_cmb,
                "closing_time_comp_raw": record.closing_time_comp_raw, "closing_time_comp_et": record.closing_time_comp_et,
                "closing_time_noncomp_raw": record.closing_time_noncomp_raw, "closing_time_noncomp_et": record.closing_time_noncomp_et,
                "source_timezone": record.source_timezone, "offering_amount_usd": record.offering_amt,
                "business_key_hash": record.business_key_hash, "current_content_hash": content_hash, "current_snapshot_id": snapshot_id,
                "raw_record": raw_record,
            }
            if existing:
                payload = dict(event_values)
                payload["raw_record"] = json_text(raw_record)
                assignments = [f"{key}=CAST(:{key} AS jsonb)" if key == "raw_record" else f"{key}=:{key}" for key in event_values if key != "auction_event_id"]
                connection.execute(text(f"UPDATE ust.auction_event SET {','.join(assignments)},last_seen_at=clock_timestamp() WHERE auction_event_id=:auction_event_id"), payload)
            else:
                _insert(connection, "auction_event", event_values, {"raw_record"})
            result_map = {
                "stop_metric_code": "stop_metric_code", "stop_metric_label": "stop_metric_label", "stop_value": "stop_value",
                "high_discount_rate": "high_discnt_rate", "high_investment_rate": "high_investment_rate",
                "high_discount_margin": "high_discnt_margin", "high_yield": "high_yield", "spread": "spread", "interest_rate": "int_rate",
                "price_per_100": "price_per100", "high_price": "high_price", "bid_to_cover_ratio": "bid_to_cover_ratio",
                "allocation_percentage": "allocation_pctage", "total_tendered_usd": "total_tendered", "total_accepted_usd": "total_accepted",
                "competitive_tendered_usd": "comp_tendered", "competitive_accepted_usd": "comp_accepted", "noncompetitive_accepted_usd": "noncomp_accepted",
                "pdf_filename_announcement": "pdf_filenm_announcemt", "pdf_filename_comp_results": "pdf_filenm_comp_results",
                "pdf_filename_noncomp_results": "pdf_filenm_noncomp_results", "xml_filename_announcement": "xml_filenm_announcemt",
                "xml_filename_comp_results": "xml_filenm_comp_results",
            }
            result_values = {column: getattr(record, field) for column, field in result_map.items()}
            result_values["auction_event_id"] = event_id
            _upsert_child(connection, "auction_result", result_values, "auction_event_id")
            allocation_fields = (
                "primary_dealer_tendered", "primary_dealer_accepted", "direct_bidder_tendered", "direct_bidder_accepted",
                "indirect_bidder_tendered", "indirect_bidder_accepted", "soma_tendered", "soma_accepted", "soma_holdings",
                "fima_noncomp_tendered", "fima_noncomp_accepted",
            )
            allocation_values = {f"{field}_usd": getattr(record, field) for field in allocation_fields}
            allocation_values.update(auction_event_id=event_id, treasury_retail_accepted_usd=record.treas_retail_accepted)
            _upsert_child(connection, "auction_bidder_allocation", allocation_values, "auction_event_id")
            previous = connection.execute(text(
                "SELECT typed_record,revision_number FROM ust.auction_revision WHERE auction_event_id=:id AND is_current"
            ), {"id": event_id}).first()
            typed = record.model_dump(mode="json")
            change_fields = [key for key in typed if not previous or previous[0].get(key) != typed[key]]
            connection.execute(text("UPDATE ust.auction_revision SET is_current=false,valid_to=clock_timestamp() WHERE auction_event_id=:id AND is_current"), {"id": event_id})
            _insert(connection, "auction_revision", {
                "auction_event_id": event_id, "revision_number": previous[1] + 1 if previous else 1,
                "content_hash": content_hash, "source_snapshot_id": snapshot_id, "raw_record": raw_record, "typed_record": typed,
                "change_fields": change_fields,
            }, {"raw_record", "typed_record"})
            self._lineage(connection, event_id, snapshot_id)
            return event_id, "UPDATED" if existing else "INSERTED"

    @staticmethod
    def _lineage(connection: Connection, event_id: UUID, snapshot_id: UUID | None) -> None:
        if snapshot_id:
            connection.execute(text(
                "INSERT INTO ust.normalized_record_lineage(entity_type,entity_id,source_snapshot_id,parser_version,confidence) "
                "VALUES('auction_event',:event_id,:snapshot_id,:parser,1) ON CONFLICT DO NOTHING"
            ), {"event_id": event_id, "snapshot_id": snapshot_id, "parser": AUCTION_PARSER_VERSION})

    def validation_report(self) -> dict[str, int]:
        auction_checks = {
            "duplicate_auction_business_keys": "SELECT count(*) FROM (SELECT cusip,auction_date,issue_date FROM ust.auction_event GROUP BY 1,2,3 HAVING count(*)>1) x",
            "multiple_current_revisions": "SELECT count(*) FROM (SELECT auction_event_id FROM ust.auction_revision WHERE is_current GROUP BY 1 HAVING count(*)>1) x",
            "allocation_exceeds_total": "SELECT count(*) FROM ust.auction_result r JOIN ust.auction_bidder_allocation a USING(auction_event_id) WHERE COALESCE(a.indirect_bidder_accepted_usd,0)+COALESCE(a.direct_bidder_accepted_usd,0)+COALESCE(a.primary_dealer_accepted_usd,0)>r.total_accepted_usd",
            "accepted_exceeds_tendered": "SELECT count(*) FROM ust.auction_result WHERE total_accepted_usd>total_tendered_usd OR competitive_accepted_usd>competitive_tendered_usd",
            "invalid_auction_dates": "SELECT count(*) FROM ust.auction_event WHERE maturity_date<=issue_date OR auction_date>issue_date",
            "invalid_allocation_percentage": "SELECT count(*) FROM ust.auction_result WHERE allocation_percentage NOT BETWEEN 0 AND 100",
            "unmapped_stop_with_value": "SELECT count(*) FROM ust.auction_result WHERE stop_metric_code='UNMAPPED' AND stop_value IS NOT NULL",
            "dashboard_ratio_mismatch": "SELECT count(*) FROM ust.v_auction_dashboard WHERE bid_to_cover_display_pct<>bid_to_cover_ratio*100",
            "missing_issue_date": "SELECT count(*) FROM ust.auction_event WHERE issue_date IS NULL",
        }
        with self.engine.connect() as connection:
            return {name: int(connection.execute(text(sql)).scalar_one()) for name, sql in auction_checks.items()}
