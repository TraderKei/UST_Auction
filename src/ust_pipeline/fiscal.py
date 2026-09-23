from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

from .http_client import TreasuryHttpClient


AUCTIONS_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/"
    "fiscal_service/v1/accounting/od/auctions_query"
)

AUCTION_FIELDS = (
    "record_date,cusip,security_type,security_term,security_term_day_month,"
    "security_term_week_year,original_security_term,series,inflation_index_security,"
    "floating_rate,announcemt_date,auction_date,issue_date,maturity_date,"
    "original_issue_date,closing_time_comp,closing_time_noncomp,auction_format,"
    "offering_amt,reopening,cash_management_bill_cmb,high_discnt_rate,"
    "high_investment_rate,high_discnt_margin,high_yield,spread,int_rate,"
    "price_per100,high_price,bid_to_cover_ratio,allocation_pctage,total_tendered,"
    "total_accepted,comp_tendered,comp_accepted,noncomp_accepted,"
    "primary_dealer_tendered,primary_dealer_accepted,direct_bidder_tendered,"
    "direct_bidder_accepted,indirect_bidder_tendered,indirect_bidder_accepted,"
    "treas_retail_accepted,soma_tendered,soma_accepted,soma_holdings,"
    "fima_noncomp_tendered,fima_noncomp_accepted,pdf_filenm_announcemt,"
    "pdf_filenm_comp_results,pdf_filenm_noncomp_results,xml_filenm_announcemt,"
    "xml_filenm_comp_results"
)


@dataclass(frozen=True)
class FiscalPage:
    page_number: int
    rows: list[dict[str, Any]]
    meta: dict[str, Any]
    links: dict[str, Any]
    raw_bytes: bytes
    request_url: str
    response_headers: dict[str, str]


class FiscalDataClient:
    def __init__(self, http: TreasuryHttpClient, page_size: int = 1000) -> None:
        self.http = http
        self.page_size = page_size

    def iter_auction_pages(self, start: date, end: date) -> Iterator[FiscalPage]:
        page_number = 1
        total_pages: int | None = None
        while total_pages is None or page_number <= total_pages:
            params: dict[str, str | int] = {
                "fields": AUCTION_FIELDS,
                "filter": (
                    f"auction_date:gte:{start.isoformat()},"
                    f"auction_date:lte:{end.isoformat()}"
                ),
                "sort": "auction_date,cusip,issue_date",
                "format": "json",
                "page[number]": page_number,
                "page[size]": self.page_size,
            }
            response = self.http.get(AUCTIONS_URL, params=params)
            raw = response.content
            payload = json.loads(raw, parse_float=str, parse_int=str)
            meta = payload.get("meta") or {}
            links = payload.get("links") or {}
            if page_number == 1:
                total_pages = int(meta["total-pages"]) if meta.get("total-pages") is not None else None
            elif total_pages is not None and meta.get("total-pages") is not None and int(meta["total-pages"]) != total_pages:
                raise ValueError("API page count changed during traversal; rerun overlapping interval")
            yield FiscalPage(
                page_number=page_number,
                rows=payload.get("data") or [],
                meta=meta,
                links=links,
                raw_bytes=raw,
                request_url=str(response.request.url),
                response_headers=dict(response.headers),
            )
            if (total_pages is not None and page_number >= total_pages) or (total_pages is None and not links.get("next")):
                break
            page_number += 1
