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
from .qra.discovery import QraLink
from .qra.parsers import PARSER_VERSION, ParseResult
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


def _upsert_fact(connection: Connection, table: str, values: dict[str, Any], conflict: str) -> None:
    columns = list(values)
    json_columns = {column for column in columns if column == "source_locator"}
    expressions = [f"CAST(:{column} AS jsonb)" if column in json_columns else f":{column}" for column in columns]
    payload = {key: json_text(value) if key in json_columns else value for key, value in values.items()}
    conflict_columns = {item.strip() for item in conflict.split(",")}
    updates = ",".join(f"{column}=EXCLUDED.{column}" for column in columns if column not in conflict_columns)
    connection.execute(text(
        f"INSERT INTO ust.{table} ({','.join(columns)}) VALUES ({','.join(expressions)}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    ), payload)


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
            "status", "finished_at", "pages_attempted", "pages_succeeded", "documents_attempted", "documents_succeeded",
            "rows_received", "rows_inserted", "rows_updated", "rows_unchanged", "rows_rejected", "checkpoint", "error_summary", "documents_review_required",
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
        fetched_at: datetime | None = None, meta: dict[str, Any] | None = None, link: QraLink | None = None,
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
                "source_url": url, "final_url": final_url or url, "discovered_on_url": link.discovered_on_url if link else None,
                "anchor_text": link.anchor_text if link else None, "content_sha256": raw.sha256,
                "mime_type": headers.get("content-type", "application/octet-stream"), "content_length": raw.size_bytes,
                "etag": headers.get("etag"), "last_modified": headers.get("last-modified"), "fetched_at": fetched_at,
                "raw_storage_uri": str(raw.path.resolve()), "parser_version": PARSER_VERSION if source == "QRA" else AUCTION_PARSER_VERSION,
                "response_meta": meta or {},
            }, {"response_meta"})
            return snapshot_id

    def conditional_headers(self, url: str) -> tuple[str | None, str | None]:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT s.etag,s.last_modified FROM ust.source_snapshot s JOIN ust.qra_document_version v USING(source_snapshot_id) "
                "WHERE s.source_url=:url AND v.is_current AND v.parser_version=:parser "
                "AND v.parse_status IN ('PARSED','RAW_ONLY','REVIEW_REQUIRED') ORDER BY s.fetched_at DESC LIMIT 1"
            ), {"url": url, "parser": PARSER_VERSION}).first()
        return (row[0], row[1]) if row else (None, None)

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

    def upsert_refunding(self, year: int, month: int, source_url: str, release: datetime | None, next_release: date | None) -> UUID:
        with self.engine.begin() as connection:
            qra_id = connection.execute(text(
                "INSERT INTO ust.qra_refunding(refunding_year,refunding_month,release_datetime,source_page_url,next_scheduled_release_date,calendar_quarter) "
                "VALUES(:year,:month,:release,:url,:next,:quarter) ON CONFLICT(refunding_year,refunding_month) DO UPDATE SET "
                "release_datetime=COALESCE(EXCLUDED.release_datetime,ust.qra_refunding.release_datetime),"
                "next_scheduled_release_date=COALESCE(EXCLUDED.next_scheduled_release_date,ust.qra_refunding.next_scheduled_release_date),"
                "updated_at=clock_timestamp() RETURNING qra_refunding_id"
            ), {"year": year, "month": month, "release": release, "url": source_url, "next": next_release, "quarter": (month - 1) // 3 + 1}).scalar_one()
            connection.execute(text("UPDATE ust.qra_refunding SET fiscal_year=:fy,fiscal_quarter=:fq WHERE qra_refunding_id=:id"),
                               {"fy":year+(month>=10), "fq":((month+2)%12)//3+1,"id":qra_id})
            connection.execute(text("""WITH p AS (SELECT qra_refunding_id,lag(qra_refunding_id) OVER(ORDER BY refunding_year,refunding_month) AS prior FROM ust.qra_refunding)
             UPDATE ust.qra_refunding r SET prior_qra_refunding_id=p.prior FROM p WHERE r.qra_refunding_id=p.qra_refunding_id"""))
            return qra_id

    def save_qra_document(
        self, qra_id: UUID, link: QraLink, snapshot_id: UUID, content_hash: str, parsed: ParseResult
    ) -> tuple[UUID, bool, str]:
        with self.engine.begin() as connection:
            document_id = connection.execute(text(
                "INSERT INTO ust.qra_document(qra_refunding_id,canonical_url,document_type,anchor_text,discovered_on_url,release_datetime) "
                "VALUES(:qra,:url,:type,:anchor,:discovered,:release) ON CONFLICT(qra_refunding_id,canonical_url) DO UPDATE SET "
                "last_seen_at=clock_timestamp() RETURNING qra_document_id"
            ), {"qra": qra_id, "url": link.url, "type": link.document_type, "anchor": link.anchor_text,
                "discovered": link.discovered_on_url, "release": link.release_datetime}).scalar_one()
            current = connection.execute(text(
                "SELECT qra_document_version_id,version_number,content_sha256,parser_version,parse_status FROM ust.qra_document_version WHERE qra_document_id=:id AND is_current FOR UPDATE"
            ), {"id": document_id}).first()
            if current and current[2].strip() == content_hash and current[3] == PARSER_VERSION and current[4] == parsed.status:
                return current[0], False, "UNCHANGED"
            action = "UPDATED" if current else "INSERTED"
            version_id = uuid4()
            connection.execute(text("UPDATE ust.qra_document_version SET is_current=false WHERE qra_document_id=:id AND is_current"), {"id": document_id})
            _insert(connection, "qra_document_version", {
                "qra_document_version_id": version_id, "qra_document_id": document_id, "source_snapshot_id": snapshot_id,
                "version_number": current[1] + 1 if current else 1, "content_sha256": content_hash, "parser_version": PARSER_VERSION,
                "parse_status": parsed.status, "parsed_at": datetime.now(UTC), "parse_summary": parsed.serializable(),
            }, {"parse_summary"})
            connection.execute(text("UPDATE ust.qra_document SET current_version_id=:version WHERE qra_document_id=:id"), {"version": version_id, "id": document_id})
            if parsed.status != "PARSED":
                return version_id, True, action
            old_versions = "SELECT qra_document_version_id FROM ust.qra_document_version WHERE qra_document_id=:document AND qra_document_version_id<>:version"
            for table in (
                "qra_borrowing_estimate", "qra_auction_size", "qra_supply", "qra_financing_mix",
                "qra_tga_path", "qra_guidance", "qra_tentative_auction", "qra_buyback_operation",
                "qra_dealer_survey", "qra_buyback_policy",
            ):
                connection.execute(text(
                    f"DELETE FROM ust.{table} WHERE qra_document_version_id IN ({old_versions})"
                ), {"document": document_id, "version": version_id})
            self._load_qra_records(connection, qra_id, version_id, parsed)
            connection.execute(text("""UPDATE ust.qra_financing_mix m SET end_tga_usd=b.end_cash_balance_usd,
                input_record_ids=ARRAY[b.qra_borrowing_estimate_id],
                source_locator=m.source_locator || jsonb_build_object('end_tga_source_record_id',b.qra_borrowing_estimate_id,'end_tga_source_version_id',b.qra_document_version_id)
                FROM ust.qra_borrowing_estimate b WHERE m.qra_refunding_id=:q AND b.qra_refunding_id=m.qra_refunding_id
                AND b.period_start=m.period_start AND b.value_class=m.value_class"""), {"q":qra_id})
            connection.execute(text("""UPDATE ust.qra_refunding r SET covered_period_start=s.start_date,covered_period_end=s.end_date
                FROM (SELECT min(auction_month) AS start_date,(max(auction_month)+interval '1 month - 1 day')::date AS end_date
                FROM ust.qra_auction_size WHERE qra_refunding_id=:q AND value_class='OFFICIAL_ESTIMATE' AND source_authority='US_TREASURY') s
                WHERE r.qra_refunding_id=:q AND s.start_date IS NOT NULL"""), {"q":qra_id})
            return version_id, True, action

    @staticmethod
    def _load_qra_records(connection: Connection, qra_id: UUID, version_id: UUID, parsed: ParseResult) -> None:
        if parsed.status not in {"PARSED"}:
            return
        if parsed.document_type not in {
            "TENTATIVE_AUCTION_XML", "TENTATIVE_BUYBACK_XML", "FINANCING_ESTIMATES_HTML",
            "POLICY_STATEMENT_HTML", "TREASURY_PRESENTATION_PDF", "TBAC_RECOMMENDED_FINANCING_PDF", "PRIMARY_DEALER_SURVEY_PDF",
        }:
            return
        if parsed.document_type == "FINANCING_ESTIMATES_HTML":
            import calendar
            from datetime import datetime as dt
            for index, record in enumerate(parsed.records):
                months, year_string = record["period_label"].rsplit(" ", 1)
                first, last = months.split("-")
                year = int(year_string)
                start_month = dt.strptime(first, "%B").month
                end_month = dt.strptime(last, "%B").month
                delta = record.get("change_from_prior_usd")
                values = {
                    "qra_refunding_id": qra_id, "qra_document_version_id": version_id, "calendar_year": year,
                    "calendar_quarter": (start_month - 1) // 3 + 1, "fiscal_year": year + (1 if start_month >= 10 else 0),
                    "fiscal_quarter": ((start_month + 2) % 12) // 3 + 1,
                    "period_start": date(year, start_month, 1), "period_end": date(year, end_month, calendar.monthrange(year, end_month)[1]),
                    "borrowing_amount_usd": record["borrowing_amount_usd"], "end_cash_balance_usd": record["end_cash_balance_usd"],
                    "prior_estimate_usd": record["borrowing_amount_usd"] - delta if delta is not None else None,
                    "change_from_prior_usd": delta, "change_reason": record.get("reason_text"),
                    "value_class": record["value_class"], "source_authority": record["source_authority"],
                    "source_locator": asdict(parsed.evidence[index]) if index < len(parsed.evidence) else {},
                }
                _upsert_fact(connection, "qra_borrowing_estimate", values,
                             "qra_refunding_id,calendar_year,calendar_quarter,value_class,qra_document_version_id")
                qra_month = connection.execute(text("SELECT refunding_month FROM ust.qra_refunding WHERE qra_refunding_id=:q"), {"q": qra_id}).scalar_one()
                point_type = "ACTUAL_START" if record["value_class"] == "OFFICIAL_ACTUAL" else "NEXT_QUARTER_END_ASSUMPTION" if start_month > qra_month else "QUARTER_END_ASSUMPTION"
                _upsert_fact(connection, "qra_tga_path", {
                    "qra_refunding_id": qra_id, "qra_document_version_id": version_id, "observation_date": values["period_end"],
                    "point_type": point_type, "balance_usd": record["end_cash_balance_usd"], "value_class": record["value_class"],
                    "source_authority": record["source_authority"], "source_locator": values["source_locator"],
                }, "qra_refunding_id,observation_date,point_type,value_class")
            return
        if parsed.document_type == "PRIMARY_DEALER_SURVEY_PDF":
            for index, record in enumerate(parsed.records):
                header = {k: record[k] for k in ("survey_as_of_date", "survey_as_of_month", "date_precision", "target_fiscal_year", "target_period_start", "target_period_end", "value_class", "source_authority")}
                header.update(qra_refunding_id=qra_id, qra_document_version_id=version_id, validation_status="VERIFIED")
                _upsert_fact(connection, "qra_dealer_survey", header, "qra_refunding_id,survey_as_of_month,target_period_end")
                survey_id = connection.execute(text("SELECT qra_dealer_survey_id FROM ust.qra_dealer_survey WHERE qra_refunding_id=:q AND survey_as_of_month=:m AND target_period_end=:e"), {"q":qra_id,"m":record["survey_as_of_month"],"e":record["target_period_end"]}).scalar_one()
                values = {k:record[k] for k in ("security_type", "normalized_security_term", "reopening", "scenario", "statistic", "current_auction_size_usd", "expected_auction_size_usd")}
                values.update(qra_dealer_survey_id=survey_id, source_locator=asdict(parsed.evidence[index]))
                _upsert_fact(connection, "qra_dealer_survey_value", values, "qra_dealer_survey_id,security_type,normalized_security_term,reopening,statistic,scenario")
            return
        if parsed.document_type in {"POLICY_STATEMENT_HTML", "TREASURY_PRESENTATION_PDF", "TBAC_RECOMMENDED_FINANCING_PDF"}:
            mappings = {
                "AUCTION_SIZE": ("qra_auction_size", "qra_refunding_id,auction_month,security_type,normalized_security_term,reopening,size_status,value_class"),
                "GUIDANCE": ("qra_guidance", "qra_refunding_id,instrument_group,evidence_text"),
                "TGA": ("qra_tga_path", "qra_refunding_id,observation_date,point_type,value_class"),
                "FINANCING_MIX": ("qra_financing_mix", "qra_refunding_id,period_start,value_class"),
                "SUPPLY": ("qra_supply", "qra_refunding_id,period_start,security_type,normalized_security_term,value_class"),
                "BUYBACK_POLICY": ("qra_buyback_policy", "qra_refunding_id,operation_purpose,value_class"),
            }
            for index, record in enumerate(parsed.records):
                values = {key: value for key, value in record.items() if key != "record_type"}
                values.update(qra_refunding_id=qra_id, qra_document_version_id=version_id,
                              source_locator=asdict(parsed.evidence[index]) if index < len(parsed.evidence) else {})
                if record["record_type"] == "FINANCING_MIX":
                    values["input_record_ids"] = []
                if record["record_type"] == "SUPPLY":
                    values["dv01_method_id"] = connection.execute(text("SELECT derived_metric_method_id FROM ust.derived_metric_method WHERE method_code='DV01_10Y_EQUIVALENT_PROXY' AND version='ui_proxy_v1'")).scalar_one()
                table, conflict = mappings[record["record_type"]]
                _upsert_fact(connection, table, values, conflict)
            connection.execute(text("""
                INSERT INTO ust.derived_metric_result(derived_metric_method_id,entity_type,entity_id,source_document_version_id,metric_value,input_record_ids,input_values,formula,rounding_rule)
                SELECT s.dv01_method_id,'qra_supply',s.qra_supply_id,s.qra_document_version_id,s.net_issuance_usd*p.numeric_value,
                ARRAY[s.qra_supply_id],jsonb_build_object('net_issuance_usd',s.net_issuance_usd,'tenor_weight',p.numeric_value),
                m.formula,m.rounding_rule FROM ust.qra_supply s JOIN ust.derived_metric_method m ON m.derived_metric_method_id=s.dv01_method_id
                JOIN ust.derived_metric_method_parameter p ON p.derived_metric_method_id=m.derived_metric_method_id AND p.parameter_key=s.normalized_security_term
                WHERE s.qra_document_version_id=:v ON CONFLICT DO NOTHING
            """), {"v": version_id})
            return
        table = "qra_tentative_auction" if parsed.document_type == "TENTATIVE_AUCTION_XML" else "qra_buyback_operation"
        for index, record in enumerate(parsed.records):
            values = dict(record)
            if table == "qra_tentative_auction":
                for field in ("reopening", "tips", "floating_rate"):
                    values[field] = parse_yes_no(values.get(field))
            values.update(qra_refunding_id=qra_id, qra_document_version_id=version_id,
                          source_locator=asdict(parsed.evidence[index]) if index < len(parsed.evidence) else {})
            columns = list(values)
            expr = ["CAST(:source_locator AS jsonb)" if key == "source_locator" else f":{key}" for key in columns]
            payload = {key: json_text(value) if key == "source_locator" else value for key, value in values.items()}
            updates = ",".join(f"{key}=EXCLUDED.{key}" for key in columns if key not in {"qra_refunding_id"})
            conflict = "qra_refunding_id,auction_date,security_type,security_term,reopening" if table == "qra_tentative_auction" else "qra_refunding_id,operation_date,purchase_bucket_name,operation_type,operation_start_time_et"
            connection.execute(text(f"INSERT INTO ust.{table} ({','.join(columns)}) VALUES ({','.join(expr)}) ON CONFLICT({conflict}) DO UPDATE SET {updates}"), payload)

    def validation_report(self, *, auction_only: bool = False) -> dict[str, int]:
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
        qra_checks = {
            "multiple_current_qra_versions": "SELECT count(*) FROM (SELECT qra_document_id FROM ust.qra_document_version WHERE is_current GROUP BY 1 HAVING count(*)>1) x",
            "qra_current_pointer_mismatch": "SELECT count(*) FROM ust.qra_document d LEFT JOIN ust.qra_document_version v ON v.qra_document_version_id=d.current_version_id WHERE d.current_version_id IS NULL OR NOT v.is_current",
            "qra_supply_arithmetic_mismatch": "SELECT count(*) FROM ust.qra_supply WHERE gross_issuance_usd IS NOT NULL AND maturing_amount_usd IS NOT NULL AND net_issuance_usd IS NOT NULL AND gross_issuance_usd-maturing_amount_usd<>net_issuance_usd",
            "qra_financing_mix_arithmetic_mismatch": "SELECT count(*) FROM ust.qra_financing_mix WHERE privately_held_net_market_borrowing_usd IS NOT NULL AND net_coupon_issuance_usd IS NOT NULL AND assumed_buybacks_usd IS NOT NULL AND implied_change_in_bills_usd IS NOT NULL AND privately_held_net_market_borrowing_usd-net_coupon_issuance_usd+assumed_buybacks_usd<>implied_change_in_bills_usd",
            "qra_tentative_invalid_dates": "SELECT count(*) FROM ust.qra_tentative_auction WHERE (announcement_date IS NOT NULL AND announcement_date>auction_date) OR (settlement_date IS NOT NULL AND settlement_date<auction_date)",
            "qra_buyback_invalid_dates": "SELECT count(*) FROM ust.qra_buyback_operation WHERE (announcement_date IS NOT NULL AND announcement_date>operation_date) OR (settlement_date IS NOT NULL AND settlement_date<operation_date)",
            "qra_missing_fact_lineage": "SELECT count(*) FROM (SELECT qra_document_version_id,source_locator FROM ust.qra_borrowing_estimate UNION ALL SELECT qra_document_version_id,source_locator FROM ust.qra_auction_size UNION ALL SELECT qra_document_version_id,source_locator FROM ust.qra_supply UNION ALL SELECT qra_document_version_id,source_locator FROM ust.qra_financing_mix UNION ALL SELECT qra_document_version_id,source_locator FROM ust.qra_tga_path UNION ALL SELECT qra_document_version_id,source_locator FROM ust.qra_guidance UNION ALL SELECT qra_document_version_id,source_locator FROM ust.qra_tentative_auction UNION ALL SELECT qra_document_version_id,source_locator FROM ust.qra_buyback_operation UNION ALL SELECT qra_document_version_id,source_locator FROM ust.qra_buyback_policy) facts WHERE qra_document_version_id IS NULL OR source_locator IS NULL OR source_locator='{}'::jsonb",
            "qra_dv01_view_mismatch": "SELECT count(*) FROM ust.v_qra_supply_monitor WHERE dv01_10y_equivalent_proxy_usd<>net_issuance_usd*tenor_weight",
        }
        checks = auction_checks if auction_only else auction_checks | qra_checks
        with self.engine.connect() as connection:
            return {name: int(connection.execute(text(sql)).scalar_one()) for name, sql in checks.items()}
