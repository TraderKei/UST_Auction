from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass
from datetime import date, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import pdfplumber
import xlrd
from lxml import etree, html
from pypdf import PdfReader


PARSER_VERSION = "qra-parser-1.2.0"
BILLION = Decimal("1000000000")


@dataclass(frozen=True)
class Evidence:
    locator_type: str
    page_number: int | None = None
    sheet_name: str | None = None
    table_title: str | None = None
    row_label: str | None = None
    column_label: str | None = None
    html_selector: str | None = None
    xml_path: str | None = None
    excerpt: str | None = None
    extraction_confidence: Decimal = Decimal("1")


@dataclass(frozen=True)
class ParseIssue:
    severity: str
    rule: str
    message: str
    locator: str | None = None


@dataclass
class ParseResult:
    document_type: str
    records: list[dict[str, Any]]
    evidence: list[Evidence]
    issues: list[ParseIssue]
    status: str = "PARSED"

    def serializable(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "records": self.records,
            "evidence": [asdict(item) for item in self.evidence],
            "issues": [asdict(item) for item in self.issues],
            "status": self.status,
        }


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _child_text(parent: etree._Element, name: str) -> str | None:
    for child in parent:
        if _local_name(child) == name:
            value = (child.text or "").strip()
            return value or None
    return None


def _decimal(value: str | None) -> Decimal | None:
    if value is None or value.strip().lower() in {"", "null", "n/a", "na", "--"}:
        return None
    cleaned = re.sub(r"[$,%()\s]", "", value)
    if value.strip().startswith("("):
        cleaned = f"-{cleaned}"
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric cell {value!r}") from exc


def _iso_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return __import__("datetime").datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"invalid date {value!r}")


def _clock(value: str | None) -> time | None:
    if not value:
        return None
    text = value.strip().upper().replace(" ET", "")
    for pattern in ("%I:%M %p", "%H:%M"):
        try:
            return __import__("datetime").datetime.strptime(text, pattern).time()
        except ValueError:
            pass
    raise ValueError(f"invalid time {value!r}")


def parse_auction_xml(content: bytes) -> ParseResult:
    root = etree.fromstring(content, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    name = _child_text(root, "AuctionCalendarName")
    start = _iso_date(_child_text(root, "StartDate"))
    end = _iso_date(_child_text(root, "EndDate"))
    records: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    issues: list[ParseIssue] = []
    for index, row in enumerate((item for item in root.iter() if _local_name(item) == "AuctionCalendarDate"), start=1):
        if not _child_text(row, "AuctionDate"):
            if not _child_text(row, 'HolidayName'):
                return ParseResult('TENTATIVE_AUCTION_XML', [], [], [ParseIssue('ERROR','XML_MISSING_AUCTION_DATE','Non-holiday row has no auction date',f'AuctionCalendarDate[{index}]')], 'QUARANTINED')
            issues.append(ParseIssue("INFO", "XML_NON_AUCTION_ROW", "Calendar holiday retained in raw", f"AuctionCalendarDate[{index}]"))
            continue
        record = {
            "calendar_name": name,
            "calendar_start_date": start,
            "calendar_end_date": end,
            "security_term": _child_text(row, "SecurityTermWeekYear"),
            "security_type": _child_text(row, "SecurityType"),
            "reopening": _child_text(row, "ReOpeningIndicator"),
            "tips": _child_text(row, "TIPS"),
            "floating_rate": _child_text(row, "FloatingRate"),
            "announcement_date": _iso_date(_child_text(row, "AnnouncementDate")),
            "auction_date": _iso_date(_child_text(row, "AuctionDate")),
            "settlement_date": _iso_date(_child_text(row, "SettlementDate")),
        }
        records.append(record)
        evidence.append(Evidence("XML_ELEMENT", row_label=f"AuctionCalendarDate[{index}]", xml_path=row.getroottree().getpath(row)))
    return ParseResult("TENTATIVE_AUCTION_XML", records, evidence, issues)


def parse_buyback_xml(content: bytes) -> ParseResult:
    root = etree.fromstring(content, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    name = _child_text(root, "BuybackCalendarName")
    start = _iso_date(_child_text(root, "StartDate"))
    end = _iso_date(_child_text(root, "EndDate"))
    records: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    for index, row in enumerate((item for item in root.iter() if _local_name(item) == "BuybackCalendarDate"), start=1):
        record = {
            "calendar_name": name,
            "calendar_start_date": start,
            "calendar_end_date": end,
            "purchase_bucket_name": _child_text(row, "PurchaseBucketName"),
            "security_type": _child_text(row, "SecurityType"),
            "operation_type": _child_text(row, "OperationType"),
            "minimum_purchase_amount_usd": _decimal(_child_text(row, "MinimumPurchaseAmountDollars")),
            "maximum_purchase_amount_usd": _decimal(_child_text(row, "MaximumPurchaseAmountDollars")),
            "maturity_date_range_start": _iso_date(_child_text(row, "MaturityDateRangeStart")),
            "maturity_date_range_end": _iso_date(_child_text(row, "MaturityDateRangeEnd")),
            "announcement_date": _iso_date(_child_text(row, "AnnouncementDate")),
            "operation_date": _iso_date(_child_text(row, "OperationDate")),
            "settlement_date": _iso_date(_child_text(row, "SettlementDate")),
            "operation_start_time_et": _clock(_child_text(row, "OperationStartTimeEasternUS")),
            "operation_end_time_et": _clock(_child_text(row, "OperationEndTimeEasternUS")),
            "source_timezone": "America/New_York",
        }
        records.append(record)
        evidence.append(Evidence("XML_ELEMENT", row_label=f"BuybackCalendarDate[{index}]", xml_path=row.getroottree().getpath(row)))
    return ParseResult("TENTATIVE_BUYBACK_XML", records, evidence, [])


def extract_html_tables(content: bytes | str) -> ParseResult:
    root = html.fromstring(content)
    records: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    issues: list[ParseIssue] = []
    for table_index, table in enumerate(root.xpath("//table"), start=1):
        caption_values = table.xpath("./caption//text()")
        title = " ".join(" ".join(caption_values).split()) or f"table-{table_index}"
        rows = table.xpath(".//tr")
        if not rows:
            continue
        header_row_index = next(
            (index for index, row in enumerate(rows) if row.xpath("./th")), 0
        )
        headers = [" ".join(cell.text_content().split()) for cell in rows[header_row_index].xpath("./th|./td")]
        if not any(headers):
            issues.append(ParseIssue("WARN", "HTML_TABLE_HEADERS", "table has no labels", title))
            continue
        for row_index, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
            cells = [" ".join(cell.text_content().split()) for cell in row.xpath("./th|./td")]
            if not cells:
                continue
            if len(cells) != len(headers):
                issues.append(
                    ParseIssue("WARN", "HTML_TABLE_WIDTH", f"expected {len(headers)} cells, got {len(cells)}", f"{title}/row-{row_index}")
                )
                continue
            records.append({"table_title": title, "values": dict(zip(headers, cells, strict=True))})
            evidence.append(
                Evidence(
                    "HTML_TABLE",
                    table_title=title,
                    row_label=cells[0],
                    html_selector=f"table:nth-of-type({table_index}) tr:nth-of-type({row_index})",
                )
            )
    return ParseResult("GENERIC_HTML_TABLES", records, evidence, issues)


def parse_financing_estimates_html(content: bytes | str) -> ParseResult:
    root = html.fromstring(content)
    paragraphs = [" ".join(node.text_content().split()) for node in root.xpath("//main//p|//main//li|//article//p|//article//li")]
    if not paragraphs:
        paragraphs = [" ".join(root.text_content().split())]
    records: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    current_pattern = re.compile(
        r"During the ([A-Za-z]+)[–-]([A-Za-z]+) (20\d{2}) quarter, Treasury (expects to borrow|borrowed) "
        r"\$([\d,.]+) billion.*?(?:assuming|ended the quarter with) an? (?:end-of-[A-Za-z]+ )?cash balance of \$([\d,.]+) billion",
        re.I,
    )
    for index, paragraph in enumerate(paragraphs, start=1):
        match = current_pattern.search(paragraph)
        if not match:
            continue
        value_class = "OFFICIAL_ACTUAL" if match.group(4).lower() == "borrowed" else "OFFICIAL_ESTIMATE"
        prior_match = re.search(r"\$([\d,.]+) billion (higher|lower) than announced", paragraph, re.I)
        if value_class == "OFFICIAL_ACTUAL":
            prior_match = None  # Excluding-cash counterfactuals are not revisions to the actual estimate.
        records.append(
            {
                "period_label": f"{match.group(1)}-{match.group(2)} {match.group(3)}",
                "borrowing_amount_usd": _decimal(match.group(5)) * BILLION,
                "end_cash_balance_usd": _decimal(match.group(6)) * BILLION,
                "change_from_prior_usd": (_decimal(prior_match.group(1)) * BILLION * (-1 if prior_match.group(2).lower() == "lower" else 1) if prior_match else None),
                "value_class": value_class,
                "source_authority": "US_TREASURY",
                "reason_text": paragraph if prior_match else None,
            }
        )
        evidence.append(Evidence("HTML_PARAGRAPH", html_selector=f"paragraph-or-list[{index}]", excerpt=paragraph[:500]))
    issues = [] if records else [ParseIssue("ERROR", "FINANCING_ESTIMATE_NOT_FOUND", "No explicit borrowing estimate paragraph matched")]
    return ParseResult("FINANCING_ESTIMATES_HTML", records, evidence, issues, "PARSED" if records else "QUARANTINED")


def parse_policy_statement_html(content: bytes | str) -> ParseResult:
    root = html.fromstring(content)
    records: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    issues: list[ParseIssue] = []
    release_match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}", " ".join(root.text_content().split()))
    release_date = __import__("datetime").datetime.strptime(release_match.group(0), "%B %d, %Y").date() if release_match else None
    tables = extract_html_tables(content)
    for table_index, table in enumerate(tables.records):
        values = table["values"]
        headers = list(values)
        term_headers = [header for header in headers if re.fullmatch(r"(?:2|3|5|7|10|20|30)-Year", header, re.I) or header.upper() == "FRN"]
        month_label = next((values[header] for header in headers if header.strip() in {"", "Month"}), None) or next(iter(values.values()), None)
        month_match = re.fullmatch(r"([A-Za-z]{3})-(\d{2})", str(month_label or ""))
        if not term_headers or not month_match:
            continue
        month_date = __import__("datetime").datetime.strptime(month_match.group(0), "%b-%y").date().replace(day=1)
        status = "ACTUAL" if release_date and month_date < release_date.replace(day=1) else "ANTICIPATED"
        for header in term_headers:
            amount = _decimal(values.get(header))
            if amount is None:
                continue
            records.append({
                "record_type": "AUCTION_SIZE", "auction_month": month_date,
                "security_type": "FRN" if header.upper() == "FRN" else "Nominal coupon",
                "normalized_security_term": "2Y" if header.upper() == "FRN" else header.upper().replace("-YEAR", "Y"),
                "reopening": None, "size_status": status, "auction_size_usd": amount * BILLION,
                "value_class": "OFFICIAL_ACTUAL" if status == "ACTUAL" else "OFFICIAL_ESTIMATE",
                "source_authority": "US_TREASURY",
            })
            evidence.append(Evidence("HTML_TABLE", table_title=table["table_title"], row_label=str(month_label), column_label=header, html_selector=f"table[{table_index + 1}]"))

    sections: dict[str, str] = {}
    for heading in root.xpath("//h2|//h3|//h4"):
        title = " ".join(heading.text_content().split()).upper()
        if not any(key in title for key in ("NOMINAL COUPON", "TIPS FINANCING", "BILL ISSUANCE")):
            continue
        parts: list[str] = []
        for sibling in heading.itersiblings():
            if sibling.tag in {"h2", "h3", "h4"}:
                break
            parts.append(" ".join(sibling.text_content().split()))
        sections[title] = " ".join(parts)
    for title, paragraph in sections.items():
        groups = ["NOMINAL_COUPON", "FRN"] if "NOMINAL COUPON" in title else ["TIPS"] if "TIPS" in title else ["BILL"]
        # Retain explicit sentences; no free-form summaries or date constants.
        sentences = re.split(r"(?<=\.)\s+", paragraph)
        facts = []
        for sentence in sentences:
            if re.search(r"Treasury (?:anticipates|plans|expects|intends)", sentence, re.I):
                status = "MAINTAIN" if re.search(r"maintain|unchanged", sentence, re.I) else "DECREASE" if re.search(r"reduc|decreas", sentence, re.I) else "INCREASE" if re.search(r"increas", sentence, re.I) else "OTHER"
                facts.append((status, sentence))
        if not facts:
            facts = [("OTHER", paragraph)]
            issues.append(ParseIssue("WARN", "GUIDANCE_REVIEW", "No explicit guidance verb; source paragraph retained", title))
        for group, (status, sentence) in ((g, f) for g in groups for f in facts):
            records.append({
                "record_type": "GUIDANCE", "instrument_group": group, "guidance_status": status,
                "effective_period": sentence, "evidence_text": sentence,
                "value_class": "OFFICIAL_ESTIMATE", "source_authority": "US_TREASURY",
            })
            evidence.append(Evidence("HTML_PARAGRAPH", row_label=title, excerpt=paragraph[:1000]))

    full_text = " ".join(root.text_content().split())
    quarter_end = re.search(r"\$([\d,.]+) billion cash balance at the end of ([A-Za-z]+)", full_text, re.I)
    peak = re.search(r"peak at \$([\d.]+) trillion \(plus or minus \$([\d,.]+) billion\) in late ([A-Za-z]+)", full_text, re.I)
    if quarter_end and release_date:
        month = __import__("datetime").datetime.strptime(quarter_end.group(2), "%B").month
        year = release_date.year + (1 if month < release_date.month - 6 else 0)
        records.append({"record_type": "TGA", "observation_date": date(year, month, __import__("calendar").monthrange(year, month)[1]),
                        "point_type": "QUARTER_END_ASSUMPTION", "balance_usd": _decimal(quarter_end.group(1)) * BILLION,
                        "range_low_usd": None, "range_high_usd": None, "value_class": "OFFICIAL_ESTIMATE", "source_authority": "US_TREASURY"})
        evidence.append(Evidence("HTML_PARAGRAPH", row_label="CASH BALANCE", excerpt=quarter_end.group(0)))
    if peak and release_date:
        month = __import__("datetime").datetime.strptime(peak.group(3), "%B").month
        year = release_date.year + (1 if month < release_date.month else 0)
        balance = _decimal(peak.group(1)) * Decimal("1000") * BILLION
        spread = _decimal(peak.group(2)) * BILLION
        records.append({"record_type": "TGA", "observation_date": date(year, month, __import__("calendar").monthrange(year, month)[1]),
                        "point_type": "INTERMEDIATE_PEAK", "balance_usd": balance, "range_low_usd": balance - spread,
                        "range_high_usd": balance + spread, "value_class": "OFFICIAL_ESTIMATE", "source_authority": "US_TREASURY"})
        evidence.append(Evidence("HTML_PARAGRAPH", row_label="CASH BALANCE", excerpt=peak.group(0)))
    for cap in re.finditer(r"up to \$([\d,.]+) billion (?:(?!up to \$).){0,160}?\bfor (liquidity support|cash management)", full_text, re.I):
        records.append({"record_type": "BUYBACK_POLICY", "operation_purpose": cap.group(2).upper().replace(" ", "_"),
                        "maximum_amount_usd": _decimal(cap.group(1)) * BILLION, "evidence_text": cap.group(0),
                        "value_class": "OFFICIAL_ESTIMATE", "source_authority": "US_TREASURY"})
        evidence.append(Evidence("HTML_PARAGRAPH", row_label="BUYBACKS", excerpt=cap.group(0)))
    if not records:
        issues.append(ParseIssue("ERROR", "POLICY_FACTS_NOT_FOUND", "No labeled auction-size table or explicit guidance facts matched"))
    return ParseResult("POLICY_STATEMENT_HTML", records, evidence, issues, "PARSED" if records else "QUARANTINED")


def parse_treasury_presentation_pdf(content: bytes) -> ParseResult:
    records: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    issues: list[ParseIssue] = []
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        return ParseResult("TREASURY_PRESENTATION_PDF", [], [], [ParseIssue("ERROR", "PDF_EXTRACTION_FAILED", str(exc))], "QUARANTINED")
    target_pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages):
        text_value = page.extract_text() or ""
        if "Implied Bill Funding for the Current and Next Quarters" in text_value:
            target_pages.append((index + 1, text_value))
    if not target_pages:
        return ParseResult("TREASURY_PRESENTATION_PDF", [], [], [ParseIssue("ERROR", "PRESENTATION_TABLE_NOT_FOUND", "Implied Bill Funding table not found")], "QUARANTINED")
    for page_number, text_value in target_pages:
        finance_matches = list(re.finditer(
            r"Marketable Borrowing\s*2\s*([\d,]+)\s+Net Coupon Issuance\s*([\d,]+)\s+Assumed Buybacks\s*3?\s*([\d,]+)\s+Implied Change in Bills\s*([\d,]+)",
            text_value, re.I,
        ))
        periods = list(re.finditer(r"Sources of Privately-Held Financing in FY(\d{2}) Q([1-4])\s+([A-Za-z]+)\s*-\s*([A-Za-z]+)\s+(20\d{2})", text_value, re.I))
        if len(finance_matches) != len(periods):
            issues.append(ParseIssue("ERROR", "PRESENTATION_SECTION_COUNT", f"finance sections={len(finance_matches)}, periods={len(periods)}", f"page {page_number}"))
            continue
        for section_index, (finance, period) in enumerate(zip(finance_matches, periods, strict=True)):
            year = int(period.group(5))
            start_month = __import__("datetime").datetime.strptime(period.group(3), "%B").month
            end_month = __import__("datetime").datetime.strptime(period.group(4), "%B").month
            period_start = date(year, start_month, 1)
            period_end = date(year, end_month, __import__("calendar").monthrange(year, end_month)[1])
            records.append({
                "record_type": "FINANCING_MIX", "period_start": period_start, "period_end": period_end,
                "fiscal_year": 2000 + int(period.group(1)), "fiscal_quarter": int(period.group(2)),
                "privately_held_net_market_borrowing_usd": _decimal(finance.group(1)) * BILLION,
                "net_coupon_issuance_usd": _decimal(finance.group(2)) * BILLION,
                "assumed_buybacks_usd": _decimal(finance.group(3)) * BILLION,
                "implied_change_in_bills_usd": _decimal(finance.group(4)) * BILLION,
                "end_tga_usd": None, "value_class": "OFFICIAL_ESTIMATE", "source_authority": "US_TREASURY",
                "calculation_method": "Treasury presentation: implied bills based on borrowing estimate and constant coupon issuance",
                "rounding_rule": "source USD billions converted exactly to USD",
            })
            evidence.append(Evidence("PDF_TABLE", page_number=page_number, table_title="Implied Bill Funding", row_label=f"FY{period.group(1)} Q{period.group(2)}", extraction_confidence=Decimal("0.95")))
            section_start = finance.end()
            section_end = finance_matches[section_index + 1].start() if section_index + 1 < len(finance_matches) else periods[section_index].start()
            table_text = text_value[section_start:section_end]
            if not re.search(r"Security\s+Gross\s+Maturing\s+Net", table_text):
                issues.append(ParseIssue('ERROR','SUPPLY_COLUMN_LABELS','Expected Security/Gross/Maturing/Net header order',f'page {page_number}'))
            rows = re.findall(r"^(2|3|5|7|10|20|30)-Year\s+([\d,]+)\s+([\d,]+)\s+(\(?[\d,]+\)?)\s+", table_text, re.M)
            if len(rows) != 7 or len({row[0] for row in rows}) != 7:
                issues.append(ParseIssue("ERROR", "SUPPLY_TENOR_COMPLETENESS", "Expected all seven distinct nominal coupon tenors", f"page {page_number}"))
            if _decimal(finance.group(1)) - _decimal(finance.group(2)) + _decimal(finance.group(3)) != _decimal(finance.group(4)):
                issues.append(ParseIssue("ERROR", "FINANCING_MIX_ARITHMETIC", "borrowing - coupon + buybacks != implied bills", f"page {page_number}"))
            for term, gross, maturing, net in rows:
                net_value = _decimal(net)
                records.append({
                    "record_type": "SUPPLY", "period_start": period_start, "period_end": period_end,
                    "fiscal_year": 2000 + int(period.group(1)), "fiscal_quarter": int(period.group(2)),
                    "security_type": "Nominal coupon", "normalized_security_term": f"{term}Y",
                    "gross_issuance_usd": _decimal(gross) * BILLION, "maturing_amount_usd": _decimal(maturing) * BILLION,
                    "net_issuance_usd": net_value * BILLION, "value_class": "OFFICIAL_ESTIMATE", "source_authority": "US_TREASURY",
                })
                evidence.append(Evidence("PDF_TABLE", page_number=page_number, table_title="Sources of Privately-Held Financing", row_label=f"{term}-Year", extraction_confidence=Decimal("0.95")))
                if _decimal(gross) - _decimal(maturing) != net_value:
                    issues.append(ParseIssue("ERROR", "SUPPLY_ARITHMETIC", f"{term}Y gross-maturing != net", f"page {page_number}"))
    status = "PARSED" if records and not any(issue.severity == "ERROR" for issue in issues) else "QUARANTINED"
    return ParseResult("TREASURY_PRESENTATION_PDF", records if status == "PARSED" else [], evidence, issues, status)


def parse_xls_labeled_tables(content: bytes, required_label_groups: Iterable[set[str]] | None = None) -> ParseResult:
    workbook = xlrd.open_workbook(file_contents=content)
    required_label_groups = list(required_label_groups or [])
    records: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    issues: list[ParseIssue] = []
    for sheet in workbook.sheets():
        values = [[str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)] for r in range(sheet.nrows)]
        for row_index, row in enumerate(values):
            normalized = {re.sub(r"\s+", " ", value).strip().lower() for value in row if value}
            if required_label_groups and not any(
                {label.lower() for label in labels}.issubset(normalized) for labels in required_label_groups
            ):
                continue
            if len(normalized) < 2:
                continue
            headers = [value or f"column_{idx + 1}" for idx, value in enumerate(row)]
            table_records = 0
            for data_row_index, data_row in enumerate(values[row_index + 1 :], start=row_index + 2):
                if not any(data_row):
                    if table_records:
                        break
                    continue
                records.append({"sheet_name": sheet.name, "values": dict(zip(headers, data_row, strict=True))})
                evidence.append(
                    Evidence("XLS_CELL_RANGE", sheet_name=sheet.name, row_label=data_row[0], table_title=" | ".join(headers))
                )
                table_records += 1
            if table_records:
                break
        else:
            issues.append(ParseIssue("INFO", "XLS_NO_LABELED_TABLE", "No requested label set found", sheet.name))
    status = "PARSED" if records else "QUARANTINED"
    if not any('survey' in name.lower() for name in workbook.sheet_names()):
        issues.append(ParseIssue("INFO", "XLS_NOT_DEALER_SURVEY", "Workbook sheets do not identify a dealer auction-size survey; no survey facts promoted"))
    return ParseResult("QUARTERLY_RELEASE_XLS", records, evidence, issues, status)


def parse_pdf_tables(content: bytes, document_type: str) -> ParseResult:
    records: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    issues: list[ParseIssue] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table_number, table in enumerate(page.extract_tables(), start=1):
                    if not table or len(table) < 2 or not table[0]:
                        continue
                    headers = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in table[0]]
                    if len({value.lower() for value in headers if value}) < 2:
                        continue
                    widths_ok = all(len(row) == len(headers) for row in table[1:] if row)
                    confidence = Decimal("0.90") if widths_ok else Decimal("0.55")
                    for row in table[1:]:
                        if not row or len(row) != len(headers):
                            continue
                        cells = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row]
                        records.append({"page_number": page_number, "values": dict(zip(headers, cells, strict=True))})
                        evidence.append(
                            Evidence(
                                "PDF_TABLE",
                                page_number=page_number,
                                table_title=f"table-{table_number}",
                                row_label=cells[0],
                                extraction_confidence=confidence,
                            )
                        )
    except Exception as exc:
        issues.append(ParseIssue("ERROR", "PDF_EXTRACTION_FAILED", str(exc)))
        return ParseResult(document_type, [], [], issues, "QUARANTINED")
    if not records:
        issues.append(ParseIssue("ERROR", "PDF_NO_RELIABLE_TABLE", "No labeled table could be extracted"))
        return ParseResult(document_type, [], evidence, issues, "QUARANTINED")
    if any(item.extraction_confidence < Decimal("0.75") for item in evidence):
        issues.append(ParseIssue("WARN", "PDF_LOW_CONFIDENCE", "One or more tables require review"))
        return ParseResult(document_type, records, evidence, issues, "REVIEW_REQUIRED")
    issues.append(ParseIssue("INFO", "PDF_SEMANTIC_REVIEW", "Extracted generic table needs schema and total verification before fact promotion"))
    return ParseResult(document_type, records, evidence, issues, "REVIEW_REQUIRED")


class ParserDispatcher:
    @staticmethod
    def parse(document_type: str, content: bytes) -> ParseResult:
        if document_type == "PRIMARY_DEALER_SURVEY_PDF":
            from .semantic_pdf import parse_survey_pdf
            return parse_survey_pdf(content)
        if document_type == "TBAC_RECOMMENDED_FINANCING_PDF":
            from .semantic_pdf import parse_tbac_recommended_pdf
            return parse_tbac_recommended_pdf(content)
        if document_type == "TENTATIVE_AUCTION_XML":
            return parse_auction_xml(content)
        if document_type == "TENTATIVE_BUYBACK_XML":
            return parse_buyback_xml(content)
        if document_type == "FINANCING_ESTIMATES_HTML":
            return parse_financing_estimates_html(content)
        if document_type == "POLICY_STATEMENT_HTML":
            return parse_policy_statement_html(content)
        if document_type == "TREASURY_PRESENTATION_PDF":
            return parse_treasury_presentation_pdf(content)
        if document_type.endswith("_HTML"):
            result = extract_html_tables(content)
            result.document_type = document_type
            root = html.fromstring(content)
            for paragraph in root.xpath("//main//p"):
                value = ' '.join(paragraph.text_content().split())
                if value:
                    result.records.append({'record_type':'SOURCE_PARAGRAPH','text':value})
                    result.evidence.append(Evidence('HTML_PARAGRAPH',html_selector=paragraph.getroottree().getpath(paragraph),excerpt=value))
            if not result.records:
                result.status = 'RAW_ONLY'
            return result
        if document_type == "QUARTERLY_RELEASE_XLS":
            return parse_xls_labeled_tables(content)
        if document_type.endswith("_PDF"):
            return parse_pdf_tables(content, document_type)
        return ParseResult(
            document_type,
            [],
            [],
            [ParseIssue("INFO", "NO_PARSER", "Raw document retained without a structured parser")],
            "RAW_ONLY",
        )
