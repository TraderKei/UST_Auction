"""Label-driven PDF schemas. Only validated cells become facts."""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from decimal import Decimal

import pdfplumber

from .parsers import BILLION, Evidence, ParseIssue, ParseResult, _decimal


def parse_survey_pdf(content: bytes) -> ParseResult:
    records, evidence, issues = [], [], []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                title = re.search(r"Aggregated Perspectives on Treasury Auction Sizes, ([A-Za-z]+) (20\d{2})", text)
                if not title or "trimmed mean" not in text.lower() or "($bn)" not in text:
                    continue
                as_of = datetime.strptime(" ".join(title.groups()), "%B %Y").date()
                for table in page.extract_tables():
                    header_index = next((i for i, row in enumerate(table) if row and row[0] == "Tenor"), None)
                    if header_index is None:
                        continue
                    headers, stats = table[header_index], table[header_index + 1]
                    expectations = [(i, int(m.group(1))) for i, label in enumerate(headers)
                                    if (m := re.search(r"Size Expectations\s+for FY(\d{2}) Year-End", label or ""))]
                    if not expectations:
                        continue
                    group = None
                    for row in table[header_index + 2:]:
                        label = (row[0] or "").strip()
                        if label in {"Coupons", "TIPS", "FRNs", "Bills"}:
                            group = {"Coupons": "Nominal coupon", "TIPS": "TIPS", "FRNs": "FRN", "Bills": "Bill"}[label]
                            continue
                        tenor = re.match(r"(\d+)-(year|mo|wk)", label, re.I)
                        if not tenor or not group:
                            continue
                        if len(row) != len(headers):
                            raise ValueError("survey table column count mismatch")
                        term = tenor.group(1) + {"year": "Y", "mo": "M", "wk": "W"}[tenor.group(2).lower()]
                        reopening = True if "reop" in label else False if "new" in label else None
                        for column, fy in expectations:
                            for offset, scenario in ((0, "SIZE_EXPECTATION"), (2, "LOW_RANGE"), (4, "HIGH_RANGE")):
                                for stat_offset, stat_label in ((0, "MEAN"), (1, "STD")):
                                    cell = column + offset + stat_offset
                                    if cell >= len(row) or stats[cell] != stat_label:
                                        raise ValueError("survey MEAN/STD column schema changed")
                                    amount = _decimal(row[cell])
                                    if amount is None:
                                        continue
                                    records.append({
                                        "survey_as_of_month": as_of, "survey_as_of_date": None,
                                        "date_precision": "MONTH", "target_fiscal_year": 2000 + fy,
                                        "target_period_start": date(1999 + fy, 10, 1), "target_period_end": date(2000 + fy, 9, 30),
                                        "security_type": group, "normalized_security_term": term, "reopening": reopening,
                                        "statistic": "TRIMMED_" + stat_label, "scenario": scenario,
                                        "current_auction_size_usd": None, "expected_auction_size_usd": amount * BILLION,
                                        "value_class": "PRIMARY_DEALER_SURVEY", "source_authority": "US_TREASURY_PRIMARY_DEALER_SURVEY",
                                    })
                                    evidence.append(Evidence("PDF_TABLE", page_number=page_no, table_title=title.group(0),
                                        row_label=label, column_label=f"FY{fy} Year-End / {scenario} / {stat_label} [column {cell + 1}]",
                                        extraction_confidence=Decimal("0.98")))
    except Exception as exc:
        return ParseResult("PRIMARY_DEALER_SURVEY_PDF", [], [], [ParseIssue("ERROR", "SURVEY_SCHEMA", str(exc))], "QUARANTINED")
    if not records:
        issues.append(ParseIssue("ERROR", "SURVEY_SCHEMA", "No verified dated, labeled survey cells"))
    else:
        issues.append(ParseIssue("INFO", "SURVEY_CURRENT_NOT_PROVIDED", "Future fiscal-year expectations are not current auction sizes; current/delta/timing remain NULL"))
    return ParseResult("PRIMARY_DEALER_SURVEY_PDF", records, evidence, issues, "PARSED" if records else "QUARANTINED")


def parse_tbac_recommended_pdf(content: bytes) -> ParseResult:
    records, evidence = [], []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if "TBAC RECOMMENDED" not in text or "BILLIONS OF DOLLARS" not in text:
                    continue
                for table in page.extract_tables():
                    if len(table) < 3:
                        continue
                    h1, h2 = table[0], table[1]
                    month_col = next((i for i, cell in enumerate(h1) if cell == "Auction" and h2[i] == "Month"), None)
                    if month_col is None:
                        continue
                    columns = [(i, re.match(r"(\d+)-Year", cell or ""), h2[i]) for i, cell in enumerate(h1)]
                    columns = [(i, m.group(1) + "Y", kind) for i, m, kind in columns if m and kind in {"Notes", "Bonds", "TIPS", "FRN"}]
                    if len(columns) < 7:
                        raise ValueError("TBAC expected tenor labels missing")
                    section = ""
                    for row in table[2:]:
                        if len(row) != len(h1):
                            raise ValueError("TBAC column count mismatch")
                        if row[0]:
                            section = re.sub(r"\s+", " ", row[0])
                        month = row[month_col] or ""
                        if not re.fullmatch(r"[A-Za-z]{3}-\d{2}", month):
                            continue
                        # Historical reference belongs to Treasury observations, not recommendations.
                        if "Historical" in section:
                            continue
                        if not any(token in section for token in ("Recommendations", "Provisional")):
                            raise ValueError("TBAC recommendation section label missing")
                        for col, term, kind in columns:
                            amount = _decimal(row[col])
                            if amount is None:
                                continue
                            records.append({"record_type": "AUCTION_SIZE", "auction_month": datetime.strptime(month, "%b-%y").date(),
                                "security_type": kind if kind in {"TIPS", "FRN"} else "Nominal coupon",
                                "normalized_security_term": term, "reopening": None, "size_status": "ANTICIPATED",
                                "auction_size_usd": amount * BILLION, "value_class": "TBAC_RECOMMENDATION", "source_authority": "TBAC"})
                            evidence.append(Evidence("PDF_TABLE", page_number=page_no, table_title=section, row_label=month,
                                column_label=f"{term} {kind}", extraction_confidence=Decimal("0.95")))
    except Exception as exc:
        return ParseResult("TBAC_RECOMMENDED_FINANCING_PDF", [], [], [ParseIssue("ERROR", "TBAC_SCHEMA", str(exc))], "QUARANTINED")
    return ParseResult("TBAC_RECOMMENDED_FINANCING_PDF", records, evidence,
        [] if records else [ParseIssue("ERROR", "TBAC_SCHEMA", "No verified recommendation table")], "PARSED" if records else "QUARANTINED")
