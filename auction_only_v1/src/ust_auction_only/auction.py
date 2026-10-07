from __future__ import annotations

import hashlib
import json
import re
from datetime import date, time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


NULL_STRINGS = {"", "null"}
DATE_FIELDS = {
    "record_date",
    "announcemt_date",
    "auction_date",
    "issue_date",
    "maturity_date",
    "original_issue_date",
}
DECIMAL_FIELDS = {
    "offering_amt",
    "high_discnt_rate",
    "high_investment_rate",
    "high_discnt_margin",
    "high_yield",
    "spread",
    "int_rate",
    "price_per100",
    "high_price",
    "bid_to_cover_ratio",
    "allocation_pctage",
    "total_tendered",
    "total_accepted",
    "comp_tendered",
    "comp_accepted",
    "noncomp_accepted",
    "primary_dealer_tendered",
    "primary_dealer_accepted",
    "direct_bidder_tendered",
    "direct_bidder_accepted",
    "indirect_bidder_tendered",
    "indirect_bidder_accepted",
    "treas_retail_accepted",
    "soma_tendered",
    "soma_accepted",
    "soma_holdings",
    "fima_noncomp_tendered",
    "fima_noncomp_accepted",
}


def sql_null(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in NULL_STRINGS:
        return None
    return value.strip() if isinstance(value, str) else value


def parse_decimal(value: Any) -> Decimal | None:
    value = sql_null(value)
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("$", ""))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal: {value!r}") from exc


def parse_date(value: Any) -> date | None:
    value = sql_null(value)
    return date.fromisoformat(str(value)) if value is not None else None


def parse_yes_no(value: Any) -> bool | None:
    value = sql_null(value)
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"yes", "y", "true", "1"}:
        return True
    if normalized in {"no", "n", "false", "0"}:
        return False
    raise ValueError(f"invalid yes/no value: {value!r}")


def parse_et_time(value: Any) -> time | None:
    value = sql_null(value)
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).strip().upper()).replace(" ET", "")
    for pattern in (r"^(\d{1,2}):(\d{2})\s*([AP]M)$", r"^(\d{1,2}):(\d{2})$"):
        match = re.match(pattern, text)
        if not match:
            continue
        hour, minute = int(match.group(1)), int(match.group(2))
        if len(match.groups()) == 3 and match.group(3):
            hour = hour % 12 + (12 if match.group(3) == "PM" else 0)
        return time(hour, minute)
    raise ValueError(f"invalid ET time: {value!r}")


def normalize_term(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip()).upper()
    replacements = {
        "YEAR": "Y",
        "YEARS": "Y",
        "YR": "Y",
        "MONTH": "M",
        "MONTHS": "M",
        "WEEK": "W",
        "WEEKS": "W",
        "DAY": "D",
        "DAYS": "D",
    }
    match = re.match(r"^(\d+)[ -]?(YEAR|YEARS|YR|MONTH|MONTHS|WEEK|WEEKS|DAY|DAYS|Y|M|W|D)$", text)
    if match:
        return f"{int(match.group(1))}{replacements.get(match.group(2), match.group(2))}"
    return text.replace("-", "")


class AuctionRecord(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    record_date: date
    cusip: str = Field(min_length=1, max_length=20)
    security_type: str
    source_security_type: str | None = None
    security_term: str
    normalized_security_term: str
    security_term_day_month: str | None = None
    security_term_week_year: str | None = None
    original_security_term: str | None = None
    series: str | None = None
    inflation_index_security: bool | None = None
    floating_rate: bool | None = None
    announcemt_date: date | None = None
    auction_date: date
    issue_date: date | None = None
    maturity_date: date | None = None
    original_issue_date: date | None = None
    closing_time_comp_raw: str | None = None
    closing_time_comp_et: time | None = None
    closing_time_noncomp_raw: str | None = None
    closing_time_noncomp_et: time | None = None
    source_timezone: Literal["America/New_York"] = "America/New_York"
    auction_format: str | None = None
    offering_amt: Decimal | None = None
    reopening: bool | None = None
    cash_management_bill_cmb: bool | None = None
    high_discnt_rate: Decimal | None = None
    high_investment_rate: Decimal | None = None
    high_discnt_margin: Decimal | None = None
    high_yield: Decimal | None = None
    spread: Decimal | None = None
    int_rate: Decimal | None = None
    price_per100: Decimal | None = None
    high_price: Decimal | None = None
    bid_to_cover_ratio: Decimal | None = None
    allocation_pctage: Decimal | None = None
    total_tendered: Decimal | None = None
    total_accepted: Decimal | None = None
    comp_tendered: Decimal | None = None
    comp_accepted: Decimal | None = None
    noncomp_accepted: Decimal | None = None
    primary_dealer_tendered: Decimal | None = None
    primary_dealer_accepted: Decimal | None = None
    direct_bidder_tendered: Decimal | None = None
    direct_bidder_accepted: Decimal | None = None
    indirect_bidder_tendered: Decimal | None = None
    indirect_bidder_accepted: Decimal | None = None
    treas_retail_accepted: Decimal | None = None
    soma_tendered: Decimal | None = None
    soma_accepted: Decimal | None = None
    soma_holdings: Decimal | None = None
    fima_noncomp_tendered: Decimal | None = None
    fima_noncomp_accepted: Decimal | None = None
    stop_metric_code: str | None = None
    stop_metric_label: str | None = None
    stop_value: Decimal | None = None
    pdf_filenm_announcemt: str | None = None
    pdf_filenm_comp_results: str | None = None
    pdf_filenm_noncomp_results: str | None = None
    xml_filenm_announcemt: str | None = None
    xml_filenm_comp_results: str | None = None

    @field_validator("security_type", "security_term", "cusip")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @property
    def business_key(self) -> tuple[str, date, date | None]:
        return self.cusip, self.auction_date, self.issue_date

    @property
    def business_key_hash(self) -> str:
        material = "|".join(
            [self.cusip, self.auction_date.isoformat(), self.issue_date.isoformat() if self.issue_date else ""]
        )
        return hashlib.sha256(material.encode()).hexdigest()

    def canonical_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=False)
        for key, value in self.model_dump().items():
            if isinstance(value, Decimal):
                payload[key] = format(value.normalize(), 'f') if value else '0'
        # Raw clock spelling lives in snapshots/revisions, not in the typed content identity.
        payload.pop('closing_time_comp_raw', None)
        payload.pop('closing_time_noncomp_raw', None)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def stop_mapping(values: dict[str, Any]) -> tuple[str, str, Decimal | None]:
    security_type = str(values.get("security_type") or "").upper()
    if parse_yes_no(values.get("floating_rate")) is True or security_type == "FRN":
        return "HIGH_DISCOUNT_MARGIN", "High discount margin", parse_decimal(values.get("high_discnt_margin"))
    if parse_yes_no(values.get("inflation_index_security")) is True or security_type == "TIPS":
        return "HIGH_REAL_YIELD", "High real yield", parse_decimal(values.get("high_yield"))
    if security_type == "BILL" or parse_yes_no(values.get("cash_management_bill_cmb")) is True:
        return "HIGH_DISCOUNT_RATE", "High discount rate", parse_decimal(values.get("high_discnt_rate"))
    if security_type in {"NOTE", "BOND"}:
        return "HIGH_YIELD", "High yield", parse_decimal(values.get("high_yield"))
    return "UNMAPPED", "Unmapped stop", None


def normalize_auction(raw: dict[str, Any]) -> AuctionRecord:
    clean = {key: sql_null(value) for key, value in raw.items()}
    for key in DATE_FIELDS:
        if key in clean:
            clean[key] = parse_date(clean[key])
    for key in DECIMAL_FIELDS:
        if key in clean:
            clean[key] = parse_decimal(clean[key])
    for key in ("inflation_index_security", "floating_rate", "reopening", "cash_management_bill_cmb"):
        if key in clean:
            clean[key] = parse_yes_no(clean[key])
    clean["source_security_type"] = clean.get("security_type")
    if clean.get("floating_rate") is True:
        clean["security_type"] = "FRN"
    elif clean.get("inflation_index_security") is True:
        clean["security_type"] = "TIPS"
    comparison_term = str(clean["security_term"])
    if clean.get("security_type") in {"Note", "Bond", "TIPS", "FRN"} and clean.get("original_security_term"):
        comparison_term = str(clean["original_security_term"])
    clean["normalized_security_term"] = normalize_term(comparison_term)
    clean["closing_time_comp_raw"] = clean.pop("closing_time_comp", None)
    clean["closing_time_noncomp_raw"] = clean.pop("closing_time_noncomp", None)
    clean["closing_time_comp_et"] = parse_et_time(clean["closing_time_comp_raw"])
    clean["closing_time_noncomp_et"] = parse_et_time(clean["closing_time_noncomp_raw"])
    code, label, value = stop_mapping(raw)
    clean.update(stop_metric_code=code, stop_metric_label=label, stop_value=value)
    return AuctionRecord.model_validate(clean)
