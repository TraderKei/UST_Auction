import json
from decimal import Decimal

import xlwt

from ust_pipeline.metrics import dv01_proxy
from ust_pipeline.qra.discovery import canonicalize_url, discover_qra_index
from ust_pipeline.qra.parsers import (
    ParserDispatcher,
    extract_html_tables,
    parse_auction_xml,
    parse_buyback_xml,
    parse_pdf_tables,
    parse_policy_statement_html,
    parse_treasury_presentation_pdf,
    parse_xls_labeled_tables,
)


SEED = "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/most-recent-quarterly-refunding-documents"


def test_relative_link_canonicalization_and_document_discovery(fixture_dir):
    index = discover_qra_index((fixture_dir / "qra_index_2026q3.html").read_bytes(), SEED)
    by_type = {link.document_type: link for link in index.links}
    assert canonicalize_url(SEED, "/system/files/221/example.xml#part") == "https://home.treasury.gov/system/files/221/example.xml"
    assert by_type["TENTATIVE_AUCTION_XML"].url.endswith("TentativeAuctionScheduleQ32026.xml")
    assert by_type["QUARTERLY_RELEASE_XLS"].refunding_quarter == 3
    assert by_type["POLICY_STATEMENT_HTML"].release_datetime.hour == 8
    assert all("Fact-Sheet-Department-of-Education" not in link.url for link in index.links)
    assert index.next_release_dates[0].isoformat() == "2026-10-16"


def test_official_auction_and_buyback_xml_are_structured(fixture_dir):
    auctions = parse_auction_xml((fixture_dir / "auction_schedule_2026q3.xml").read_bytes())
    buybacks = parse_buyback_xml((fixture_dir / "buyback_schedule_2026q3.xml").read_bytes())
    assert auctions.status == "PARSED" and len(auctions.records) >= 1
    assert {"security_term", "announcement_date", "auction_date", "settlement_date"} <= auctions.records[0].keys()
    assert buybacks.status == "PARSED" and len(buybacks.records) >= 1
    assert buybacks.records[0]["source_timezone"] == "America/New_York"
    assert isinstance(buybacks.records[0]["maximum_purchase_amount_usd"], Decimal)


def test_optional_xml_elements_are_null():
    content = b"""<AuctionCalendar><AuctionCalendarName>x</AuctionCalendarName><StartDate>08/01/2026</StartDate><EndDate>08/31/2026</EndDate><AuctionCalendarDate><SecurityType>BILL</SecurityType><AuctionDate>08/10/2026</AuctionDate></AuctionCalendarDate></AuctionCalendar>"""
    record = parse_auction_xml(content).records[0]
    assert record["security_term"] is None
    assert record["settlement_date"] is None


def test_html_table_is_label_based_when_columns_reorder():
    first = extract_html_tables(b"<table><tr><th>Term</th><th>Amount</th></tr><tr><td>2Y</td><td>69</td></tr></table>")
    second = extract_html_tables(b"<table><tr><th>Amount</th><th>Term</th></tr><tr><td>69</td><td>2Y</td></tr></table>")
    assert first.records[0]["values"]["Term"] == second.records[0]["values"]["Term"] == "2Y"
    assert first.records[0]["values"]["Amount"] == second.records[0]["values"]["Amount"] == "69"


def test_legacy_xls_sheet_and_label_detection(tmp_path):
    path = tmp_path / "survey.xls"
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Dealer Survey")
    for column, value in enumerate(["Narrative", "ignore"]):
        sheet.write(0, column, value)
    for column, value in enumerate(["Term", "Median", "Current"]):
        sheet.write(3, column, value)
    for column, value in enumerate(["2Y", 77.5, 69]):
        sheet.write(4, column, value)
    workbook.save(str(path))
    result = parse_xls_labeled_tables(path.read_bytes(), [{"Term", "Median"}])
    assert result.status == "PARSED"
    assert result.records[0]["sheet_name"] == "Dealer Survey"
    assert result.records[0]["values"]["Term"] == "2Y"


def test_official_quarterly_release_xls_parses_by_labels(fixture_dir):
    result = ParserDispatcher.parse("QUARTERLY_RELEASE_XLS", (fixture_dir / "quarterly_release_2026q3.bin").read_bytes())
    assert result.status == "PARSED"
    assert any(record["sheet_name"] == "Net marketable borrowing " for record in result.records)


def test_broken_pdf_is_quarantined():
    result = parse_pdf_tables(b"not-a-pdf", "TREASURY_PRESENTATION_PDF")
    assert result.status == "QUARANTINED"
    assert result.issues[0].rule == "PDF_EXTRACTION_FAILED"


def test_official_policy_statement_extracts_sizes_guidance_and_tga(fixture_dir):
    result = parse_policy_statement_html((fixture_dir / "policy_statement_2026q3.html").read_bytes())
    assert result.status == "PARSED"
    assert sum(record["record_type"] == "AUCTION_SIZE" for record in result.records) == 48
    assert {record["instrument_group"] for record in result.records if record["record_type"] == "GUIDANCE"} == {"NOMINAL_COUPON", "FRN", "TIPS", "BILL"}
    peak = next(record for record in result.records if record.get("point_type") == "INTERMEDIATE_PEAK")
    assert peak["balance_usd"] == Decimal("1050000000000.00")
    assert peak["range_low_usd"] == Decimal("1000000000000.00")


def test_2026_presentation_specific_parser_when_local_source_is_available():
    pdf = __import__("pathlib").Path(__file__).parent / "fixtures" / "treasury_presentation_2026q3.pdf"
    if not pdf.exists():
        __import__("pytest").skip("large official PDF is not committed as a fixture")
    result = parse_treasury_presentation_pdf(pdf.read_bytes())
    assert result.status == "PARSED"
    supply = [record for record in result.records if record["record_type"] == "SUPPLY"][:7]
    assert sum(record["gross_issuance_usd"] for record in supply) == Decimal("954000000000")
    assert sum(record["net_issuance_usd"] for record in supply) == Decimal("366000000000")


def test_2026_q3_fixture_relationships_are_regression_only(fixture_dir):
    facts = json.loads((fixture_dir / "qra_facts_2026q3.json").read_text(encoding="utf-8"), parse_float=Decimal)
    assert facts["fixture_only"] is True
    assert facts["borrowing"]["current"] - facts["borrowing"]["prior"] == facts["borrowing"]["delta"] == 68
    assert sum(facts["supply"]["gross"]) == 954
    assert sum(facts["supply"]["net"]) == 366
    proxies = [dv01_proxy(Decimal(str(net)), Decimal(str(weight))) for net, weight in zip(facts["supply"]["net"], facts["supply"]["weights"], strict=True)]
    assert proxies == [Decimal("3.00"), Decimal("16.80"), Decimal("25.00"), Decimal("50.40"), Decimal("66.00"), Decimal("69.30"), Decimal("133.25")]
    assert facts["financing_mix"] == [
        {"implied_bills": 409, "net_coupon": 375, "assumed_buybacks": 45},
        {"implied_bills": 317, "net_coupon": 361, "assumed_buybacks": 50},
    ]
