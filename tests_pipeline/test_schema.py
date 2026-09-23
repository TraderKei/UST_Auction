import hashlib
import os
from pathlib import Path

import pytest
from pglast import parse_sql
from sqlalchemy import create_engine, text

from ust_pipeline.auction import normalize_auction
from ust_pipeline.repository import Repository


ROOT = Path(__file__).parents[1]


def test_postgresql_ddl_parses_and_contains_contract_objects():
    ddl = (ROOT / "db" / "ust_pipeline_schema.sql").read_text(encoding="utf-8")
    assert len(parse_sql(ddl)) >= 50
    for table in (
        "ingestion_run", "source_request", "source_snapshot", "data_quality_issue", "security_master", "auction_event",
        "auction_result", "auction_bidder_allocation", "auction_revision", "qra_refunding", "qra_document",
        "qra_document_version", "qra_borrowing_estimate", "qra_auction_size", "qra_financing_mix", "qra_tga_path",
        "qra_tentative_auction", "qra_buyback_operation", "qra_dealer_survey", "qra_dealer_survey_value", "derived_metric_method",
    ):
        assert f"CREATE TABLE ust.{table}" in ddl
    for view in ("v_auction_dashboard", "v_auction_prior_comparable", "v_qra_supply_monitor", "v_qra_comparison", "v_qra_tga_path", "v_qra_dealer_outlook"):
        assert f"CREATE VIEW ust.{view}" in ddl
    assert "ui_proxy_v1" in ddl and "is_official_treasury_metric" in ddl


def test_read_only_ui_baseline_hash_when_available():
    baseline = Path(r"C:\Users\KOSCOM\Documents\UST_Bidding\UST_AUCTION_ui-baseline-v2.html")
    if not baseline.exists():
        pytest.skip("baseline exists only on the specified workstation")
    assert hashlib.sha256(baseline.read_bytes()).hexdigest().upper() == "D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E"


@pytest.mark.integration
def test_postgres_ddl_constraints_views_and_idempotent_upsert(fixture_dir):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to an empty disposable PostgreSQL 16 database")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS ust CASCADE")
    repository = Repository(engine=engine)
    repository.init_schema(ROOT / "db" / "ust_pipeline_schema.sql")
    import json
    raw = json.loads((fixture_dir / "auctions_page_1.json").read_text(encoding="utf-8"))["data"][0]
    record = normalize_auction(raw)
    assert repository.upsert_auction(record, raw, None)[1] == "INSERTED"
    assert repository.upsert_auction(record, raw, None)[1] == "UNCHANGED"
    corrected = dict(raw, bid_to_cover_ratio="9.99")
    assert repository.upsert_auction(normalize_auction(corrected), corrected, None)[1] == "UPDATED"
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM ust.auction_event")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM ust.auction_revision")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM ust.v_auction_dashboard")).scalar_one() == 1
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA ust CASCADE")

