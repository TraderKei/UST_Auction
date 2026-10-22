from pathlib import Path

import pytest

from scripts.acquire_tentative_schedule_v1 import build_html, snapshot_from_xml


FIXTURE = Path(__file__).parent / "fixtures" / "auction_schedule_2026q3.xml"
SOURCE = "https://home.treasury.gov/system/files/221/TentativeAuctionScheduleQ32026.xml"


def test_versioned_builder_preserves_source_and_schedule_fields():
    snapshot = snapshot_from_xml(FIXTURE.read_bytes(), SOURCE, "2026-09-03")
    html = build_html(snapshot)
    assert snapshot["calendarEnd"] == "2027-01-30"
    assert len(snapshot["rows"]) == 213
    assert any(row["auctionDate"] == "2026-11-19" and row["tips"] == "Y" for row in snapshot["rows"])
    assert 'id="ust-tentative-schedule-v1"' in html
    assert 'window.__UST_MERGE_TENTATIVE__(rows, officialUpcoming, todayText, upcomingTo)' in html
    assert '공고 확인 필요' in html


def test_invalid_xml_does_not_generate_a_versioned_html():
    with pytest.raises(Exception):
        snapshot_from_xml(b"not XML", SOURCE, "2026-09-03")
