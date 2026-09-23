"""Offline fixture tests against a disposable PostgreSQL 16 database."""
from copy import deepcopy
import hashlib
import json
import os
from datetime import date, datetime, UTC
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from ust_pipeline.auction import normalize_auction
from ust_pipeline.qra.discovery import QraLink
from ust_pipeline.qra.parsers import Evidence, ParserDispatcher, ParseResult, ParseIssue
from ust_pipeline.raw_store import RawStore
from ust_pipeline.repository import Repository

ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.integration


@pytest.fixture
def repo():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL must point to a disposable PostgreSQL 16 DB")
    engine = create_engine(url)
    with engine.begin() as c:
        assert int(c.exec_driver_sql("SHOW server_version_num").scalar_one()) >= 160000
        c.exec_driver_sql("DROP SCHEMA IF EXISTS ust CASCADE")
    repository = Repository(engine=engine)
    repository.init_schema(ROOT / "db/ust_pipeline_schema.sql")
    yield repository
    engine.dispose()


def test_announcement_result_reversion_and_same_cusip_reopening(repo, fixture_dir):
    raw = json.loads((fixture_dir / "auctions_page_1.json").read_text())["data"][0]
    announcement = dict(raw, high_discnt_rate="null", high_yield="null", high_discnt_margin="null", bid_to_cover_ratio="null")
    assert repo.upsert_auction(normalize_auction(announcement), announcement, None)[1] == "INSERTED"
    assert repo.upsert_auction(normalize_auction(announcement), announcement, None)[1] == "UNCHANGED"
    assert repo.upsert_auction(normalize_auction(raw), raw, None)[1] == "UPDATED"
    assert repo.upsert_auction(normalize_auction(announcement), announcement, None)[1] == "UPDATED"
    reopening = dict(raw, auction_date="2026-08-05", issue_date="2026-08-10", maturity_date="2027-08-10", reopening="Yes")
    assert repo.upsert_auction(normalize_auction(reopening), reopening, None)[1] == "INSERTED"
    with repo.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM ust.auction_event")).scalar_one() == 2
        assert c.execute(text("SELECT count(*) FROM ust.auction_revision")).scalar_one() == 4
        assert repo.validation_report()["duplicate_auction_business_keys"] == 0


def test_qra_twice_with_lineage_classes_corrections_and_quarantine(repo, fixture_dir, tmp_path):
    run = repo.start_run("QRA", "FIXTURE")
    qra = repo.upsert_refunding(2026, 8, "https://home.treasury.gov/", datetime(2026,8,5,12,30,tzinfo=UTC), date(2026,11,4))
    fixtures = [
        ("financing_estimates_2026q3.html", "FINANCING_ESTIMATES_HTML"),
        ("policy_statement_2026q3.html", "POLICY_STATEMENT_HTML"),
        ("treasury_presentation_2026q3.pdf", "TREASURY_PRESENTATION_PDF"),
        ("tbac_recommended_2026q3.pdf", "TBAC_RECOMMENDED_FINANCING_PDF"),
        ("auction_schedule_2026q3.xml", "TENTATIVE_AUCTION_XML"),
        ("buyback_schedule_2026q3.xml", "TENTATIVE_BUYBACK_XML"),
        ("dealer_survey_2026q2.pdf", "PRIMARY_DEALER_SURVEY_PDF"),
    ]
    for filename, kind in fixtures:
        content = (fixture_dir / filename).read_bytes()
        link = QraLink("https://home.treasury.gov/system/files/221/" + filename, filename, kind, "https://home.treasury.gov/", None, 2026,3)
        stored = RawStore(tmp_path).put(content, "qra", "application/octet-stream")
        snapshot = repo.save_snapshot(run, "QRA", link.url, stored, {})
        parsed = ParserDispatcher.parse(kind, content)
        assert parsed.status == "PARSED", (filename, parsed.issues)
        assert repo.save_qra_document(qra, link, snapshot, stored.sha256, parsed)[1]
        assert not repo.save_qra_document(qra, link, snapshot, stored.sha256, parsed)[1]
    with repo.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM ust.qra_document_version")).scalar_one() == 7
        assert c.execute(text("SELECT count(*) FROM ust.qra_tentative_auction")).scalar_one() == 213
        assert c.execute(text("SELECT count(*) FROM ust.qra_buyback_operation")).scalar_one() == 18
        assert c.execute(text("SELECT count(*) FROM ust.qra_dealer_survey_value")).scalar_one() == 450
        assert c.execute(text("SELECT count(*) FROM ust.qra_auction_size WHERE value_class='TBAC_RECOMMENDATION'")).scalar_one() == 54
        assert c.execute(text("SELECT count(*) FROM ust.qra_auction_size WHERE source_authority='US_TREASURY'")).scalar_one() == 48
        assert c.execute(text("SELECT sum(gross_issuance_usd) FROM ust.v_qra_supply_monitor WHERE fiscal_year=2026")).scalar_one() == Decimal("954000000000")
        assert c.execute(text("SELECT count(*) FROM ust.derived_metric_result")).scalar_one() == 14
        assert c.execute(text("SELECT borrowing_change_usd FROM ust.v_qra_comparison WHERE calendar_quarter=3")).scalar_one() == Decimal("68000000000")
        assert c.execute(text("SELECT balance_usd FROM ust.qra_tga_path WHERE point_type='ACTUAL_START'")).scalar_one() == Decimal("919000000000")
        assert c.execute(text("SELECT count(*) FROM ust.qra_buyback_policy")).scalar_one()==2
        assert c.execute(text("SELECT end_tga_usd FROM ust.qra_financing_mix WHERE fiscal_year=2026")).scalar_one()==Decimal('950000000000')
        survey = c.execute(text("SELECT expected_auction_size_usd,current_auction_size_usd,pct_change FROM ust.v_qra_dealer_outlook WHERE normalized_security_term='2Y' AND security_type='Nominal coupon' AND target_fiscal_year=2027 AND statistic='TRIMMED_MEAN' AND scenario='SIZE_EXPECTATION'")).one()
        assert survey == (Decimal("77500000000"), None, None)
        assert c.execute(text("""SELECT count(*) FROM (
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_borrowing_estimate UNION ALL
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_auction_size UNION ALL
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_supply UNION ALL
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_financing_mix UNION ALL
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_tga_path UNION ALL
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_guidance UNION ALL
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_tentative_auction UNION ALL
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_buyback_operation UNION ALL
            SELECT qra_document_version_id,value_class,source_authority,source_locator FROM ust.qra_buyback_policy
        ) facts WHERE qra_document_version_id IS NULL OR value_class IS NULL OR source_authority IS NULL
            OR source_locator IS NULL OR source_locator='{}'::jsonb""")).scalar_one() == 0
        assert c.execute(text("""SELECT count(*) FROM ust.qra_dealer_survey s
            WHERE qra_document_version_id IS NULL OR value_class<>'PRIMARY_DEALER_SURVEY' OR source_authority IS NULL""")).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM ust.qra_dealer_survey_value WHERE source_locator IS NULL OR source_locator='{}'::jsonb")).scalar_one() == 0
        assert c.execute(text("""SELECT count(*) FROM ust.derived_metric_result
            WHERE source_document_version_id IS NULL OR cardinality(input_record_ids)=0 OR input_values='{}'::jsonb
            OR formula IS NULL OR rounding_rule IS NULL OR value_class<>'DERIVED_UI_PROXY'""")).scalar_one() == 0
        weights = c.execute(text("""SELECT parameter_key,numeric_value FROM ust.derived_metric_method_parameter
            WHERE parameter_name='tenor_weight' ORDER BY CASE parameter_key
            WHEN '2Y' THEN 2 WHEN '3Y' THEN 3 WHEN '5Y' THEN 5 WHEN '7Y' THEN 7
            WHEN '10Y' THEN 10 WHEN '20Y' THEN 20 WHEN '30Y' THEN 30 END""")).all()
        assert weights == [
            ("2Y", Decimal("0.200000000")), ("3Y", Decimal("0.300000000")),
            ("5Y", Decimal("0.500000000")), ("7Y", Decimal("0.700000000")),
            ("10Y", Decimal("1.000000000")), ("20Y", Decimal("1.650000000")),
            ("30Y", Decimal("2.050000000")),
        ]
        assert c.execute(text("""SELECT count(*) FROM information_schema.columns WHERE table_schema='ust' AND
            (column_name IN ('when_issued','wi_rate','tail','tail_bp','market_rate','market_yield')
             OR column_name LIKE 'when_issued_%' OR column_name LIKE 'market_rate_%'
             OR column_name LIKE 'market_yield_%' OR column_name LIKE 'tail_%')""")).scalar_one() == 0
        for view in ["v_auction_dashboard", "v_auction_prior_comparable", "v_qra_supply_monitor", "v_qra_comparison", "v_qra_tga_path", "v_qra_dealer_outlook", "v_qra_auction_size_comparison", "v_ingestion_status"]:
            c.execute(text(f"SELECT * FROM ust.{view} LIMIT 2")).all()

    # A verified B revision updates current facts without duplicating rows.
    changed = deepcopy(parsed)
    changed_cell = next(record for record in changed.records if record["normalized_security_term"] == "2Y"
                        and record["security_type"] == "Nominal coupon" and record["target_fiscal_year"] == 2027
                        and record["statistic"] == "TRIMMED_MEAN" and record["scenario"] == "SIZE_EXPECTATION")
    changed_cell["expected_auction_size_usd"] = Decimal("78000000000")
    changed_raw = RawStore(tmp_path).put(b"verified dealer survey revision B", "qra", None)
    changed_snapshot = repo.save_snapshot(run, "QRA", link.url, changed_raw, {})
    assert repo.save_qra_document(qra, link, changed_snapshot, changed_raw.sha256, changed)[1]
    with repo.engine.connect() as c:
        changed_value = c.execute(text("""SELECT expected_auction_size_usd FROM ust.v_qra_dealer_outlook
            WHERE normalized_security_term='2Y' AND security_type='Nominal coupon' AND target_fiscal_year=2027
            AND statistic='TRIMMED_MEAN' AND scenario='SIZE_EXPECTATION'""")).scalar_one()
        assert changed_value == Decimal("78000000000")
        assert c.execute(text("SELECT count(*) FROM ust.qra_dealer_survey_value")).scalar_one() == 450

    # A quarantined revision retains verified B facts and all document history.
    bad = ParseResult(kind, [], [], [ParseIssue("ERROR", "BAD_PDF", "broken layout")], "QUARANTINED")
    bad_raw = RawStore(tmp_path).put(b"bad PDF revision", "qra", None)
    bad_snapshot = repo.save_snapshot(run, "QRA", link.url, bad_raw, {})
    repo.save_qra_document(qra, link, bad_snapshot, bad_raw.sha256, bad)
    with repo.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM ust.qra_dealer_survey_value")).scalar_one() == 450
        assert c.execute(text("""SELECT expected_auction_size_usd FROM ust.v_qra_dealer_outlook
            WHERE normalized_security_term='2Y' AND security_type='Nominal coupon' AND target_fiscal_year=2027
            AND statistic='TRIMMED_MEAN' AND scenario='SIZE_EXPECTATION'""")).scalar_one() == Decimal("78000000000")
    assert repo.save_qra_document(qra, link, snapshot, stored.sha256, parsed)[1]  # reversion to A
    with repo.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM ust.qra_document_version")).scalar_one() == 10
        assert c.execute(text("SELECT count(*) FROM ust.qra_dealer_survey_value")).scalar_one() == 450
        assert c.execute(text("""SELECT expected_auction_size_usd FROM ust.v_qra_dealer_outlook
            WHERE normalized_security_term='2Y' AND security_type='Nominal coupon' AND target_fiscal_year=2027
            AND statistic='TRIMMED_MEAN' AND scenario='SIZE_EXPECTATION'""")).scalar_one() == Decimal("77500000000")
        assert c.execute(text("SELECT count(*) FROM ust.qra_document_version WHERE is_current")).scalar_one() == 7


def test_qra_comparison_uses_prior_refunding_for_the_same_calendar_period(repo, tmp_path):
    run = repo.start_run("QRA", "COMPARISON_FIXTURE")
    prior_qra = repo.upsert_refunding(2026, 5, "https://home.treasury.gov/", datetime(2026, 5, 6, 12, 30, tzinfo=UTC), None)
    current_qra = repo.upsert_refunding(2026, 8, "https://home.treasury.gov/", datetime(2026, 8, 5, 12, 30, tzinfo=UTC), None)

    def save_estimate(qra_id, suffix, amount):
        content = f"official estimate {suffix}".encode()
        link = QraLink(
            f"https://home.treasury.gov/news/press-releases/{suffix}", suffix, "FINANCING_ESTIMATES_HTML",
            "https://home.treasury.gov/", None, 2026, 3,
        )
        stored = RawStore(tmp_path).put(content, "qra", "text/html")
        snapshot = repo.save_snapshot(run, "QRA", link.url, stored, {})
        parsed = ParseResult(
            "FINANCING_ESTIMATES_HTML",
            [{
                "period_label": "October-December 2026", "borrowing_amount_usd": amount,
                "end_cash_balance_usd": Decimal("850000000000"), "change_from_prior_usd": None,
                "reason_text": None, "value_class": "OFFICIAL_ESTIMATE", "source_authority": "US_TREASURY",
            }],
            [Evidence("HTML", html_selector="main p", excerpt=f"official estimate {suffix}")], [], "PARSED",
        )
        assert repo.save_qra_document(qra_id, link, snapshot, stored.sha256, parsed)[1]

    save_estimate(prior_qra, "prior-estimate", Decimal("600000000000"))
    save_estimate(current_qra, "current-estimate", Decimal("628000000000"))
    with repo.engine.connect() as c:
        row = c.execute(text("""SELECT prior_refunding_id,prior_estimate_usd,borrowing_change_usd,
            cross_document_change_usd,current_estimate_record_id,prior_estimate_record_id
            FROM ust.v_qra_comparison WHERE qra_refunding_id=:q AND calendar_year=2026 AND calendar_quarter=4"""),
            {"q": current_qra}).one()
        assert row[0] == prior_qra
        assert row[1:4] == (Decimal("600000000000"), Decimal("28000000000"), Decimal("28000000000"))
        assert row[4] is not None and row[5] is not None


def test_database_fk_unique_and_check_enforcement(repo):
    statements = [
        "INSERT INTO ust.auction_result(auction_event_id,stop_metric_code,stop_metric_label) VALUES(gen_random_uuid(),'HIGH_YIELD','x')",
        "INSERT INTO ust.qra_refunding(refunding_year,refunding_month,source_page_url) VALUES(2026,3,'x')",
        "INSERT INTO ust.derived_metric_method(method_code,version,name,description,formula,unit,effective_from) SELECT method_code,version,name,description,formula,unit,effective_from FROM ust.derived_metric_method LIMIT 1",
    ]
    for statement in statements:
        with pytest.raises(IntegrityError):
            with repo.engine.begin() as c:
                c.execute(text(statement))


def test_prior_comparable_uses_six_valid_observations_and_excludes_current(repo, fixture_dir):
    raw = json.loads((fixture_dir / "auctions_page_1.json").read_text())["data"][0]
    for day in range(1,10):
        item = dict(raw, cusip=f"FIX{day:06}", security_type="Note", security_term="10-Year", original_security_term="10-Year",
                    inflation_index_security="No", floating_rate="No", auction_date=f"2026-07-{day:02}", issue_date=f"2026-07-{day:02}",
                    maturity_date="2036-07-15", high_yield="null" if day==8 else str(day), bid_to_cover_ratio="2.48")
        repo.upsert_auction(normalize_auction(item),item,None)
    with repo.engine.connect() as c:
        row=c.execute(text("SELECT prior_stop_value,prior_six_valid_stop_average,prior_six_valid_stop_sample_count,bid_to_cover_display_pct FROM ust.v_auction_dashboard WHERE auction_date='2026-07-09'")).one()
        assert row == (Decimal(7),Decimal('4.5'),6,Decimal('248'))
