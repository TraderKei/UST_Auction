from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from ust_pipeline.auction import normalize_auction, parse_decimal, sql_null
from ust_pipeline.metrics import (
    accepted_share,
    bid_to_cover_percent,
    et_to_kst,
    other_ui_residual,
    percentage_point_change,
    valid_trailing_average,
)


def raw_record(**updates):
    value = {
        "record_date": "2026-08-03", "cusip": "91282TEST", "security_type": "Note", "security_term": "2-Year",
        "auction_date": "2026-08-25", "issue_date": "2026-08-31", "maturity_date": "2028-08-31",
        "announcemt_date": "2026-08-20", "closing_time_comp": "01:00 PM", "closing_time_noncomp": "12:00 PM",
        "inflation_index_security": "No", "floating_rate": "No", "reopening": "No", "cash_management_bill_cmb": "No",
        "offering_amt": "69000000000", "high_yield": "3.875000", "high_discnt_rate": "null",
        "high_discnt_margin": "null", "bid_to_cover_ratio": "2.48", "allocation_pctage": "21.37",
        "total_accepted": "69000000000", "indirect_bidder_accepted": "45000000000",
        "direct_bidder_accepted": "12000000000", "primary_dealer_accepted": "12000000000",
    }
    value.update(updates)
    return value


def test_null_strings_and_real_zero_remain_distinct():
    assert sql_null("null") is None
    assert sql_null("") is None
    assert sql_null(None) is None
    assert parse_decimal("0.0000000000") == Decimal("0.0000000000")


def test_decimal_and_date_normalization_without_float():
    record = normalize_auction(raw_record())
    assert record.offering_amt == Decimal("69000000000")
    assert record.auction_date.isoformat() == "2026-08-25"
    assert record.closing_time_comp_et.isoformat() == "13:00:00"
    assert record.source_timezone == "America/New_York"
    assert record.normalized_security_term == "2Y"
    assert record.stop_metric_code == "HIGH_YIELD"


@pytest.mark.parametrize(
    ("updates", "code", "value"),
    [
        ({"security_type": "Bill", "high_discnt_rate": "4.25"}, "HIGH_DISCOUNT_RATE", Decimal("4.25")),
        ({"security_type": "Bond", "high_yield": "4.50"}, "HIGH_YIELD", Decimal("4.50")),
        ({"security_type": "Note", "inflation_index_security": "Yes", "high_yield": "1.90"}, "HIGH_REAL_YIELD", Decimal("1.90")),
        ({"security_type": "Note", "floating_rate": "Yes", "high_discnt_margin": "0.115"}, "HIGH_DISCOUNT_MARGIN", Decimal("0.115")),
        ({"security_type": "Bill", "cash_management_bill_cmb": "Yes", "high_discnt_rate": "4.10"}, "HIGH_DISCOUNT_RATE", Decimal("4.10")),
    ],
)
def test_stop_mapping(updates, code, value):
    record = normalize_auction(raw_record(**updates))
    assert (record.stop_metric_code, record.stop_value) == (code, value)


def test_business_key_keeps_reissues_as_separate_auction_events():
    first = normalize_auction(raw_record(auction_date="2026-07-28", issue_date="2026-07-31", reopening="No"))
    second = normalize_auction(raw_record(auction_date="2026-08-25", issue_date="2026-08-31", reopening="Yes"))
    assert first.cusip == second.cusip
    assert first.business_key_hash != second.business_key_hash


def test_dashboard_metrics_and_valid_six_observations():
    assert bid_to_cover_percent(Decimal("2.48")) == Decimal("248.0")
    assert accepted_share(Decimal("25"), Decimal("100")) == Decimal("25.000000")
    assert accepted_share(Decimal("0"), Decimal("0")) is None
    assert percentage_point_change(Decimal("31.5"), Decimal("28.0")) == Decimal("3.5")
    assert other_ui_residual(Decimal("60"), Decimal("20"), Decimal("15")) == Decimal("5")
    assert other_ui_residual(Decimal("80"), Decimal("20"), Decimal("15")) is None
    average, sample = valid_trailing_average([Decimal("1"), None, Decimal("2"), Decimal("3"), None, Decimal("4"), Decimal("5"), Decimal("6"), Decimal("99")])
    assert (average, sample) == (Decimal("3.5"), 6)


def test_et_to_kst_applies_dst():
    winter = et_to_kst(datetime(2026, 1, 15, 13, 0, tzinfo=ZoneInfo("America/New_York")))
    summer = et_to_kst(datetime(2026, 7, 15, 13, 0, tzinfo=ZoneInfo("America/New_York")))
    assert (winter.hour, winter.day) == (3, 16)
    assert (summer.hour, summer.day) == (2, 16)
