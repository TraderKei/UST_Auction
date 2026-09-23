import json
from datetime import date

import httpx

from ust_pipeline.fiscal import AUCTIONS_URL, FiscalDataClient
from ust_pipeline.http_client import TreasuryHttpClient


def test_multi_page_iteration_and_last_page(fixture_dir):
    rows1 = json.loads((fixture_dir / "auctions_page_1.json").read_text(encoding="utf-8"))["data"]
    rows2 = json.loads((fixture_dir / "auctions_page_2.json").read_text(encoding="utf-8"))["data"]
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page[number]"])
        seen.append(page)
        rows = rows1 if page == 1 else rows2
        payload = {
            "data": rows,
            "meta": {"count": len(rows), "total-count": 4, "total-pages": 2, "labels": {"cusip": "CUSIP"}, "dataTypes": {"cusip": "STRING"}, "dataFormats": {"cusip": "String"}},
            "links": {"next": "&page[number]=2&page[size]=2" if page == 1 else None},
        }
        return httpx.Response(200, json=payload, request=request)

    http = TreasuryHttpClient("test", transport=httpx.MockTransport(handler))
    pages = list(FiscalDataClient(http, page_size=2).iter_auction_pages(date(2026, 8, 1), date(2026, 8, 31)))
    assert seen == [1, 2]
    assert [page.page_number for page in pages] == [1, 2]
    assert sum(len(page.rows) for page in pages) == 4
    assert pages[0].meta["dataTypes"]["cusip"] == "STRING"


def test_429_and_5xx_retry_then_success():
    statuses = iter([429, 503, 200])
    slept = []

    def handler(request):
        status = next(statuses)
        return httpx.Response(status, headers={"Retry-After": "0"}, json={} if status == 200 else None, request=request)

    http = TreasuryHttpClient("test", max_retries=3, transport=httpx.MockTransport(handler), sleeper=slept.append)
    assert http.get(AUCTIONS_URL).status_code == 200
    assert len(slept) == 2

