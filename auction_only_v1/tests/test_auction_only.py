"""Contract checks for the independently executable auction version."""

from __future__ import annotations

import re
import sys
import json
from decimal import Decimal
from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ust_auction_only.cli import DDL_PATH, build_parser  # noqa: E402
from ust_auction_only.config import Settings  # noqa: E402
from ust_auction_only.auction import normalize_auction  # noqa: E402
from ust_auction_only.validation import validate_auction  # noqa: E402


def test_sql_spec_and_runtime_exclude_deferred_tables() -> None:
    ddl = DDL_PATH.read_text(encoding="utf-8")
    spec = (ROOT / "docs" / "DB_SPEC.md").read_text(encoding="utf-8")
    assert len(parse_sql(ddl)) > 0
    assert DDL_PATH == ROOT / "db" / "auction_schema.sql"
    tables = re.findall(r"CREATE TABLE ust\.([a-z_]+)", ddl)
    views = re.findall(r"CREATE VIEW ust\.([a-z_]+)", ddl)
    assert len(tables) == 10
    assert set(views) == {"v_auction_dashboard", "v_auction_prior_comparable", "v_ingestion_status"}
    for name in tables:
        assert f"## {name}\n" in spec
    for name in views:
        assert f"### {name}\n" in spec
    assert "bid_to_cover_ratio IS NULL" in ddl
    assert all(name in tables for name in ("auction_event", "auction_result", "auction_revision"))


def test_cli_and_settings_only_offer_auction_work() -> None:
    help_text = build_parser().format_help()
    assert "backfill-auctions" in help_text
    assert "sync-auctions" in help_text
    assert "validate-auctions" in help_text
    assert set(build_parser()._subparsers._group_actions[0].choices) == {
        "init-db", "backfill-auctions", "sync-auctions", "validate-auctions"
    }
    assert "auction_page_size" in Settings.model_fields


def test_official_auction_fixture_normalizes_in_new_package() -> None:
    fixture = ROOT.parents[0] / "tests_pipeline" / "fixtures" / "auctions_page_1.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))["data"][0]
    record = normalize_auction(raw)
    assert record.stop_metric_code == "HIGH_DISCOUNT_RATE"
    assert record.bid_to_cover_ratio == Decimal("2.610000")
    assert not any(issue.severity == "ERROR" for issue in validate_auction(record))
