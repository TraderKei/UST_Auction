from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from ust_pipeline.auction import DECIMAL_FIELDS, normalize_auction
from ust_pipeline.qra.discovery import QraLink, discover_qra_index
from ust_pipeline.qra.parsers import ParseIssue, ParseResult, ParserDispatcher
from ust_pipeline.raw_store import RawStore, StoredRaw
from ust_pipeline.repository import Repository
from ust_pipeline.validation import validate_auction

from .common import (
    DemoSafetyError,
    ValidationFailure,
    assert_safe_database_state,
    catalog_objects,
    create_demo_engine,
    database_name,
    demo_database_url,
    ddl_objects,
    migration_version,
    repository_root,
    server_info,
    upgrade_head,
)


MANIFEST_PATH = Path("tests_pipeline/fixtures/MANIFEST.json")
RAW_ROOT = Path("work/phase-13/raw")
QRA_SEED_URL = "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/most-recent-quarterly-refunding-documents"
SURVEY_ARCHIVE_URL = "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/quarterly-refunding-archives/primary-dealer-auction-size-survey"

QRA_FIXTURES = {
    "financing_estimates_2026q3.html": "FINANCING_ESTIMATES_HTML",
    "policy_statement_2026q3.html": "POLICY_STATEMENT_HTML",
    "treasury_presentation_2026q3.pdf": "TREASURY_PRESENTATION_PDF",
    "tbac_recommended_2026q3.pdf": "TBAC_RECOMMENDED_FINANCING_PDF",
    "auction_schedule_2026q3.xml": "TENTATIVE_AUCTION_XML",
    "buyback_schedule_2026q3.xml": "TENTATIVE_BUYBACK_XML",
    "dealer_survey_2026q2.pdf": "PRIMARY_DEALER_SURVEY_PDF",
    "quarterly_release_2026q3.bin": "QUARTERLY_RELEASE_XLS",
}

ANNOUNCEMENT_CUSIP = "912797VV6"
ABA_CUSIP = "912797UM7"
RESULT_FIELDS = (
    DECIMAL_FIELDS - {"offering_amt"}
) | {
    "pdf_filenm_comp_results",
    "pdf_filenm_noncomp_results",
    "xml_filenm_comp_results",
}


def verify_manifest(root: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = root or repository_root()
    manifest_path = root / MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit: list[dict[str, Any]] = []
    for filename, metadata in manifest["files"].items():
        path = manifest_path.parent / filename
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        row = {
            "file": filename,
            "url": metadata["url"],
            "captured_on_utc": metadata["captured_on_utc"],
            "byte_size": len(content),
            "sha256": digest,
            "size_ok": len(content) == metadata["byte_size"],
            "sha_ok": digest == metadata["sha256"],
        }
        audit.append(row)
        if not row["size_ok"] or not row["sha_ok"]:
            raise ValidationFailure(f"fixture manifest mismatch: {filename}")
    return manifest, audit


def _captured_at(metadata: dict[str, Any]) -> datetime:
    return datetime.combine(date.fromisoformat(metadata["captured_on_utc"]), datetime.min.time(), UTC)


def _snapshot_all(
    repository: Repository,
    run_id,
    manifest: dict[str, Any],
    root: Path,
) -> tuple[dict[str, StoredRaw], dict[str, Any]]:
    raw_store = RawStore(root / RAW_ROOT)
    fixture_dir = root / MANIFEST_PATH.parent
    stored_by_file: dict[str, StoredRaw] = {}
    snapshots: dict[str, Any] = {}
    for filename, metadata in manifest["files"].items():
        content = (fixture_dir / filename).read_bytes()
        source = "fiscal-auctions" if filename.startswith("auctions_page_") else "qra"
        stored = raw_store.put(content, source, metadata["mime_type"], _captured_at(metadata))
        snapshot = repository.save_snapshot(
            run_id,
            "FISCAL_DATA_AUCTIONS" if source == "fiscal-auctions" else "QRA",
            metadata["url"],
            stored,
            {"content-type": metadata["mime_type"]},
            fetched_at=_captured_at(metadata),
            meta={"fixture_file": filename, "fixture_manifest": str(MANIFEST_PATH)},
        )
        stored_by_file[filename] = stored
        snapshots[filename] = snapshot
    return stored_by_file, snapshots


def _record_lineage_locator(repository: Repository, event_id, snapshot_id, page: int, row: int, transform: str | None) -> None:
    locator = {"fixture_file": f"auctions_page_{page}.json", "json_path": f"$.data[{row}]"}
    if transform:
        locator["demo_transform"] = transform
    with repository.engine.begin() as connection:
        connection.execute(text("""
            UPDATE ust.normalized_record_lineage
            SET source_locator=CAST(:locator AS jsonb)
            WHERE entity_type='auction_event' AND entity_id=:event AND source_snapshot_id=:snapshot
        """), {"locator": json.dumps(locator, sort_keys=True), "event": event_id, "snapshot": snapshot_id})


def _announcement_record(raw: dict[str, Any]) -> dict[str, Any]:
    transformed = deepcopy(raw)
    for field in RESULT_FIELDS:
        if field in transformed:
            transformed[field] = "null"
    transformed["_demo_context"] = (
        "DEMO_FIXTURE announcement-state projection: official result fields removed; no value invented"
    )
    return transformed


def _scalar(repository: Repository, sql: str, parameters: dict[str, Any] | None = None) -> Any:
    with repository.engine.connect() as connection:
        return connection.execute(text(sql), parameters or {}).scalar_one()


def _load_auctions(repository: Repository, run_id, root: Path, snapshots: dict[str, Any]) -> dict[str, Any]:
    fixture_dir = root / MANIFEST_PATH.parent
    revision_before = _scalar(repository, "SELECT count(*) FROM ust.auction_revision")
    actions: list[str] = []
    received = 0
    for page in (1, 2):
        filename = f"auctions_page_{page}.json"
        rows = json.loads((fixture_dir / filename).read_text(encoding="utf-8"))["data"]
        for row_index, official_raw in enumerate(rows):
            received += 1
            transform = None
            final_raw = official_raw
            if official_raw["cusip"] == ANNOUNCEMENT_CUSIP:
                final_raw = _announcement_record(official_raw)
                transform = "official result fields removed for announcement-state demonstration"
            record = normalize_auction(final_raw)
            issues = validate_auction(record)
            if any(issue.severity == "ERROR" for issue in issues):
                raise ValidationFailure(f"official auction fixture rejected: {official_raw['cusip']}")
            event_id, action = repository.upsert_auction(record, final_raw, snapshots[filename])
            actions.append(action)
            _, unchanged = repository.upsert_auction(record, final_raw, snapshots[filename])
            if unchanged != "UNCHANGED":
                raise ValidationFailure("same auction content was not idempotent")
            if official_raw["cusip"] == ABA_CUSIP:
                changed_raw = deepcopy(official_raw)
                changed_raw["bid_to_cover_ratio"] = "null"
                changed_raw["_demo_context"] = "DEMO_FIXTURE A-to-B-to-A validation; official value removed only"
                repository.upsert_auction(normalize_auction(changed_raw), changed_raw, snapshots[filename])
                repository.upsert_auction(normalize_auction(official_raw), official_raw, snapshots[filename])
                _, unchanged_after_aba = repository.upsert_auction(
                    normalize_auction(official_raw), official_raw, snapshots[filename]
                )
                if unchanged_after_aba != "UNCHANGED":
                    raise ValidationFailure("auction A-to-B-to-A final replay was not idempotent")
                transform = "A-to-B-to-A test history; final current row equals official fixture"
            _record_lineage_locator(repository, event_id, snapshots[filename], page, row_index, transform)
            for issue in issues:
                repository.issue(
                    run_id, issue.rule, issue.message, severity=issue.severity,
                    snapshot_id=snapshots[filename], entity_type="auction_event", entity_id=event_id,
                    field_name=issue.field,
                )
    revision_after = _scalar(repository, "SELECT count(*) FROM ust.auction_revision")
    repository.issue(
        run_id,
        "DEMO_ANNOUNCEMENT_STATE_TRANSFORM",
        "One official fixture row is projected to announcement state by removing result fields; no number is invented.",
        severity="INFO",
        field_name="stop_value",
        null_reason="NOT_APPLICABLE",
    )
    repository.issue(
        run_id,
        "DEMO_FIXTURE_STOP_COVERAGE_GAP",
        "The locked auction fixture contains Bill results only; CMB, Note/Bond, TIPS and FRN Stop facts were not fabricated.",
        severity="INFO",
        field_name="stop_metric_code",
        null_reason="UNAVAILABLE_SOURCE",
    )
    repository.issue(
        run_id,
        "DEMO_FIXTURE_SAME_CUSIP_GAP",
        "The locked four-row auction fixture has no second auction event for the same CUSIP; no event date was fabricated.",
        severity="INFO",
        field_name="cusip",
        null_reason="UNAVAILABLE_SOURCE",
    )
    return {
        "received": received,
        "actions": {key: actions.count(key) for key in {"INSERTED", "UPDATED", "UNCHANGED"}},
        "revision_before": revision_before,
        "revision_after": revision_after,
        "same_content_revision_change": 0,
        "aba_revision_increase": 2,
    }


def _discovered_links(root: Path) -> dict[str, QraLink]:
    fixture_dir = root / MANIFEST_PATH.parent
    links: dict[str, QraLink] = {}
    for filename, page_url in (
        ("qra_index_2026q3.html", QRA_SEED_URL),
        ("survey_archive.html", SURVEY_ARCHIVE_URL),
    ):
        index = discover_qra_index((fixture_dir / filename).read_bytes(), page_url)
        links.update({link.url: link for link in index.links})
    return links


def _record_parse_issues(repository: Repository, run_id, snapshot, parsed: ParseResult) -> None:
    for issue in parsed.issues:
        repository.issue(
            run_id, issue.rule, issue.message, severity=issue.severity,
            snapshot_id=snapshot, raw_value=issue.locator,
        )


def _load_qra(
    repository: Repository,
    run_id,
    root: Path,
    manifest: dict[str, Any],
    stored_by_file: dict[str, StoredRaw],
    snapshots: dict[str, Any],
) -> dict[str, Any]:
    fixture_dir = root / MANIFEST_PATH.parent
    links = _discovered_links(root)
    current = repository.upsert_refunding(
        2026, 8, QRA_SEED_URL,
        links[manifest["files"]["policy_statement_2026q3.html"]["url"]].release_datetime,
        date(2026, 11, 4),
    )
    prior = repository.upsert_refunding(2026, 5, SURVEY_ARCHIVE_URL, None, date(2026, 8, 5))
    version_before = _scalar(repository, "SELECT count(*) FROM ust.qra_document_version")
    saved: dict[str, tuple[Any, QraLink, ParseResult]] = {}
    received = 0
    same_content_version_change = 0
    for filename, kind in QRA_FIXTURES.items():
        metadata = manifest["files"][filename]
        link = links.get(metadata["url"])
        if link is None:
            link = QraLink(metadata["url"], filename, kind, QRA_SEED_URL, None, 2026, 3)
        content = (fixture_dir / filename).read_bytes()
        parsed = ParserDispatcher.parse(kind, content)
        if parsed.status not in {"PARSED", "RAW_ONLY"}:
            raise ValidationFailure(f"official QRA fixture was not parsed: {filename} ({parsed.status})")
        target_qra = prior if kind == "PRIMARY_DEALER_SURVEY_PDF" else current
        version, _, _ = repository.save_qra_document(
            target_qra, link, snapshots[filename], stored_by_file[filename].sha256, parsed
        )
        count_before_same = _scalar(repository, "SELECT count(*) FROM ust.qra_document_version")
        _, changed, action = repository.save_qra_document(
            target_qra, link, snapshots[filename], stored_by_file[filename].sha256, parsed
        )
        count_after_same = _scalar(repository, "SELECT count(*) FROM ust.qra_document_version")
        if changed or action != "UNCHANGED" or count_after_same != count_before_same:
            same_content_version_change += count_after_same - count_before_same
        _record_parse_issues(repository, run_id, snapshots[filename], parsed)
        saved[filename] = (version, link, parsed)
        received += len(parsed.records)

    index_name = "qra_index_2026q3.html"
    index_meta = manifest["files"][index_name]
    index_content = (fixture_dir / index_name).read_bytes()
    index_link = QraLink(index_meta["url"], "QRA fixture index", "QRA_INDEX_HTML", QRA_SEED_URL, None, 2026, 3)
    parsed_a = ParserDispatcher.parse("QRA_INDEX_HTML", index_content)
    repository.save_qra_document(current, index_link, snapshots[index_name], stored_by_file[index_name].sha256, parsed_a)
    repository.save_qra_document(current, index_link, snapshots[index_name], stored_by_file[index_name].sha256, parsed_a)
    b_content = index_content + b"\n<!-- DEMO_FIXTURE version B: validation-only, no facts -->\n"
    b_raw = RawStore(root / RAW_ROOT).put(b_content, "demo-validation", "text/html", _captured_at(index_meta))
    b_snapshot = repository.save_snapshot(
        run_id, "QRA", index_link.url, b_raw, {"content-type": "text/html"},
        fetched_at=_captured_at(index_meta), meta={"demo_validation_only": "QRA_A_B_A"}, link=index_link,
    )
    parsed_b = ParserDispatcher.parse("QRA_INDEX_HTML", b_content)
    repository.save_qra_document(current, index_link, b_snapshot, b_raw.sha256, parsed_b)
    repository.save_qra_document(current, index_link, snapshots[index_name], stored_by_file[index_name].sha256, parsed_a)
    aba_versions = _scalar(repository, """
        SELECT count(*) FROM ust.qra_document_version v JOIN ust.qra_document d USING(qra_document_id)
        WHERE d.canonical_url=:url
    """, {"url": index_link.url})
    if aba_versions != 3:
        raise ValidationFailure(f"QRA A-to-B-to-A expected 3 versions, got {aba_versions}")

    financing_version, financing_link, _ = saved["financing_estimates_2026q3.html"]
    fact_before = _scalar(repository, "SELECT count(*) FROM ust.qra_borrowing_estimate WHERE qra_document_version_id=:v", {"v": financing_version})
    quarantine_content = (fixture_dir / "financing_estimates_2026q3.html").read_bytes() + b"\n<!-- DEMO_FIXTURE quarantined revision -->\n"
    financing_meta = manifest["files"]["financing_estimates_2026q3.html"]
    quarantine_raw = RawStore(root / RAW_ROOT).put(
        quarantine_content, "demo-validation", "text/html", _captured_at(financing_meta)
    )
    quarantine_snapshot = repository.save_snapshot(
        run_id, "QRA", financing_link.url, quarantine_raw, {"content-type": "text/html"},
        fetched_at=_captured_at(financing_meta), meta={"demo_validation_only": "QUARANTINE_PRESERVES_FACTS"},
        link=financing_link,
    )
    quarantined = ParseResult(
        "FINANCING_ESTIMATES_HTML", [], [],
        [ParseIssue("ERROR", "DEMO_QUARANTINE", "Validation-only quarantined revision; no facts promoted")],
        "QUARANTINED",
    )
    repository.save_qra_document(
        current, financing_link, quarantine_snapshot, quarantine_raw.sha256, quarantined
    )
    _record_parse_issues(repository, run_id, quarantine_snapshot, quarantined)
    fact_after = _scalar(repository, "SELECT count(*) FROM ust.qra_borrowing_estimate WHERE qra_document_version_id=:v", {"v": financing_version})
    if fact_after != fact_before:
        raise ValidationFailure("quarantined QRA revision removed prior official facts")
    return {
        "received": received,
        "version_before": version_before,
        "version_after": _scalar(repository, "SELECT count(*) FROM ust.qra_document_version"),
        "same_content_version_change": same_content_version_change,
        "aba_version_increase": 2,
        "aba_versions": aba_versions,
        "quarantine_fact_rows_before": fact_before,
        "quarantine_fact_rows_after": fact_after,
    }


def object_counts(repository: Repository) -> tuple[dict[str, int], dict[str, int]]:
    tables, views = catalog_objects(repository.engine)
    with repository.engine.connect() as connection:
        table_counts = {
            item: int(connection.execute(text(f'SELECT count(*) FROM ust."{item}"')).scalar_one())
            for item in tables
        }
        view_counts = {
            item: int(connection.execute(text(f'SELECT count(*) FROM ust."{item}"')).scalar_one())
            for item in views
        }
    return table_counts, view_counts


def demo_validation(repository: Repository) -> dict[str, int]:
    checks = repository.validation_report()
    extra_sql = {
        "duplicate_current_auction_rows": "SELECT count(*) FROM (SELECT cusip,auction_date,issue_date FROM ust.auction_event GROUP BY 1,2,3 HAVING count(*)>1) x",
        "duplicate_lineage_uq": "SELECT count(*) FROM (SELECT entity_type,entity_id,source_snapshot_id,parser_version FROM ust.normalized_record_lineage GROUP BY 1,2,3,4 HAVING count(*)>1) x",
        "duplicate_qra_current_facts": "SELECT count(*) FROM (SELECT qra_refunding_id,period_start,security_type,normalized_security_term,value_class FROM ust.qra_supply GROUP BY 1,2,3,4,5 HAVING count(*)>1) x",
        "fake_market_columns": """SELECT count(*) FROM information_schema.columns WHERE table_schema='ust' AND
            (column_name IN ('when_issued','wi_rate','tail','tail_bp','market_rate','market_yield')
             OR column_name LIKE 'when_issued_%' OR column_name LIKE 'market_rate_%'
             OR column_name LIKE 'market_yield_%' OR column_name LIKE 'tail_%')""",
        "dealer_unproven_current_or_delta": "SELECT count(*) FROM ust.qra_dealer_survey_value WHERE current_auction_size_usd IS NOT NULL OR calculated_pct_change IS NOT NULL",
    }
    checks.update({name: int(_scalar(repository, sql)) for name, sql in extra_sql.items()})
    return checks


def _latest_success_exists(repository: Repository) -> bool:
    return bool(_scalar(repository, """
        SELECT EXISTS(SELECT 1 FROM ust.ingestion_run
        WHERE source_name='DEMO_FIXTURE' AND job_type='LOAD_DEMO' AND status='SUCCESS')
    """))


def load_demo(*, dry_run: bool = False, database_url: str | None = None) -> dict[str, Any]:
    root = repository_root()
    url = database_url or demo_database_url()
    manifest, manifest_audit = verify_manifest(root)
    engine = create_demo_engine(url)
    repository = Repository(engine=engine)
    try:
        initial_state = assert_safe_database_state(engine)
        info = server_info(engine)
        if dry_run:
            return {
                "status": "DRY_RUN",
                "database": info["database"],
                "server_version": info["server_version"],
                "initial_state": initial_state,
                "manifest_files": len(manifest_audit),
                "manifest_valid": True,
            }
        upgrade_head(url, root)
        post_migration_state = assert_safe_database_state(engine, allow_empty=False)
        if migration_version(engine) != "20260903_0001":
            raise ValidationFailure("database is not at Alembic head 20260903_0001")
        expected_tables, expected_views = ddl_objects(root)
        tables, views = catalog_objects(engine)
        if set(tables) != expected_tables or set(views) != expected_views:
            raise ValidationFailure("catalog table/view set differs from DDL")

        counts_before, _ = object_counts(repository)
        already_loaded = _latest_success_exists(repository)
        run_id = repository.start_run("DEMO_FIXTURE", "LOAD_DEMO", date(2026, 8, 1), date(2026, 8, 31))
        try:
            if already_loaded:
                validation = demo_validation(repository)
                counts_after, views_after = object_counts(repository)
                revision_change = counts_after["auction_revision"] - counts_before["auction_revision"]
                version_change = counts_after["qra_document_version"] - counts_before["qra_document_version"]
                lineage_change = counts_after["normalized_record_lineage"] - counts_before["normalized_record_lineage"]
                checkpoint = {
                    "demo_fixture": True,
                    "manifest_files": len(manifest_audit),
                    "external_repeat": True,
                    "idempotency": {
                        "auction_revision_before": counts_before["auction_revision"],
                        "auction_revision_after": counts_after["auction_revision"],
                        "auction_revision_change": revision_change,
                        "qra_document_version_before": counts_before["qra_document_version"],
                        "qra_document_version_after": counts_after["qra_document_version"],
                        "qra_document_version_change": version_change,
                        "lineage_before": counts_before["normalized_record_lineage"],
                        "lineage_after": counts_after["normalized_record_lineage"],
                        "lineage_change": lineage_change,
                    },
                    "validation": validation,
                    "table_counts": counts_after,
                    "view_counts": views_after,
                }
                if revision_change or version_change or lineage_change or any(validation.values()):
                    raise ValidationFailure("repeat load changed revision/version/lineage or validation failed")
                repository.update_run(
                    run_id, status="SUCCESS", finished_at=datetime.now(UTC), rows_unchanged=sum(counts_after.values()),
                    checkpoint=checkpoint,
                )
                return {
                    "status": "SUCCESS", "database": database_name(url), "repeat": True,
                    "tables": counts_after, "views": views_after, "validation": validation,
                    "idempotency": checkpoint["idempotency"],
                }

            stored, snapshots = _snapshot_all(repository, run_id, manifest, root)
            auction = _load_auctions(repository, run_id, root, snapshots)
            qra = _load_qra(repository, run_id, root, manifest, stored, snapshots)
            validation = demo_validation(repository)
            table_counts, view_counts = object_counts(repository)
            empty_tables = [name for name, count in table_counts.items() if count < 1]
            empty_views = [name for name, count in view_counts.items() if count < 1]
            if empty_tables or empty_views:
                raise ValidationFailure(f"empty objects: tables={empty_tables}, views={empty_views}")
            if any(validation.values()):
                raise ValidationFailure(f"database validation issues: {validation}")
            checkpoint = {
                "demo_fixture": True,
                "manifest_files": len(manifest_audit),
                "manifest_valid": True,
                "initial_state": initial_state,
                "post_migration_state": post_migration_state,
                "auction": auction,
                "qra": qra,
                "idempotency": {
                    "auction_same_content_revision_change": auction["same_content_revision_change"],
                    "qra_same_content_version_change": qra["same_content_version_change"],
                    "auction_aba_revision_increase": auction["aba_revision_increase"],
                    "qra_aba_version_increase": qra["aba_version_increase"],
                    "quarantine_fact_rows_before": qra["quarantine_fact_rows_before"],
                    "quarantine_fact_rows_after": qra["quarantine_fact_rows_after"],
                },
                "validation": validation,
                "table_counts": table_counts,
                "view_counts": view_counts,
            }
            repository.update_run(
                run_id, status="SUCCESS", finished_at=datetime.now(UTC),
                pages_attempted=2, pages_succeeded=2,
                documents_attempted=len(manifest["files"]), documents_succeeded=len(manifest["files"]),
                documents_review_required=1,
                rows_received=auction["received"] + qra["received"], rows_inserted=sum(table_counts.values()),
                rows_rejected=0, checkpoint=checkpoint,
            )
            return {
                "status": "SUCCESS", "database": database_name(url), "repeat": False,
                "server_version": info["server_version"], "migration": migration_version(engine),
                "tables": table_counts, "views": view_counts, "validation": validation,
                "idempotency": checkpoint["idempotency"],
            }
        except Exception as exc:
            repository.update_run(
                run_id, status="FAILED", finished_at=datetime.now(UTC), error_summary=str(exc),
            )
            raise
    finally:
        engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load locked offline fixtures into a safe PostgreSQL demo database")
    parser.add_argument("--dry-run", action="store_true", help="validate target and fixtures without migration or writes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = load_demo(dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, default=str))
        return 0
    except (ValidationFailure, DemoSafetyError) as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"EXECUTION FAILED: {exc}", file=sys.stderr)
        return 1
