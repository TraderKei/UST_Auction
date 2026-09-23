import os
import json
from datetime import date
from decimal import Decimal

import pytest

from ust_pipeline.auction import normalize_auction
from ust_pipeline.fiscal import FiscalDataClient
from ust_pipeline.http_client import TreasuryHttpClient
from ust_pipeline.pipeline import QRA_SEED_URL
from ust_pipeline.qra.discovery import classify_document, discover_qra_index, is_allowed_qra_url


pytestmark = pytest.mark.live


@pytest.mark.skipif(os.getenv("RUN_LIVE_SMOKE") != "1", reason="set RUN_LIVE_SMOKE=1")
def test_live_fiscal_metadata_types_and_pagination_consistency():
    with TreasuryHttpClient(
        "ust-auction-qra-pipeline-live-smoke/0.1", timeout_seconds=30,
        allowed_hosts={"api.fiscaldata.treasury.gov"},
    ) as http:
        pages = FiscalDataClient(http, page_size=2).iter_auction_pages(date(2026, 8, 1), date(2026, 8, 31))
        first = next(pages)
        assert first.rows and int(first.meta["total-count"]) >= len(first.rows)
        assert {"labels", "dataTypes", "dataFormats", "total-pages"} <= first.meta.keys()
        assert {"cusip", "auction_date", "issue_date", "security_type"} <= first.rows[0].keys()
        typed = normalize_auction(first.rows[0])
        assert isinstance(typed.auction_date, date)
        assert typed.offering_amt is None or isinstance(typed.offering_amt, Decimal)
        checked_pages = 1
        if int(first.meta["total-pages"]) > 1:
            second = next(pages)
            checked_pages = 2
            assert second.page_number == 2
            assert second.meta["total-pages"] == first.meta["total-pages"]
            assert second.meta["total-count"] == first.meta["total-count"]
        print(json.dumps({
            "source": "FISCAL_DATA_AUCTIONS", "checked_pages": checked_pages,
            "meta_total_count": int(first.meta["total-count"]),
            "meta_total_pages": int(first.meta["total-pages"]), "first_business_key": list(typed.business_key),
        }, default=str))


@pytest.mark.skipif(os.getenv("RUN_LIVE_SMOKE") != "1", reason="set RUN_LIVE_SMOKE=1")
def test_live_qra_dynamic_discovery_and_document_family_downloads():
    with TreasuryHttpClient(
        "ust-auction-qra-pipeline-live-smoke/0.1", timeout_seconds=45,
        allowed_hosts={"home.treasury.gov"},
    ) as http:
        response = http.get(QRA_SEED_URL)
        index = discover_qra_index(response.content, QRA_SEED_URL)
        families = {
            "HTML": {"FINANCING_ESTIMATES_HTML", "POLICY_STATEMENT_HTML", "TBAC_REPORT_HTML", "TBAC_MINUTES_HTML"},
            "XML": {"TENTATIVE_AUCTION_XML", "TENTATIVE_BUYBACK_XML"},
            "XLS": {"QUARTERLY_RELEASE_XLS"},
            "PDF": {
                "TBAC_RECOMMENDED_FINANCING_PDF", "TREASURY_PRESENTATION_PDF", "TBAC_CHARGE_PDF",
                "TENTATIVE_AUCTION_PDF", "TENTATIVE_BUYBACK_PDF", "PRIMARY_DEALER_AGENDA_PDF",
            },
        }
        selected = {}
        for family, document_types in families.items():
            selected[family] = next((link for link in index.links if link.document_type in document_types), None)
            assert selected[family] is not None, (family, sorted({link.document_type for link in index.links}))
        audit = {"seed_status": response.status_code, "discovered_links": len(index.links), "documents": []}
        signatures = {"HTML": (b"<!doctype", b"<html"), "XML": (b"<?xml", b"<auction", b"<buyback"),
                      "XLS": (bytes.fromhex("d0cf11e0"), b"pk\x03\x04"), "PDF": (b"%pdf",)}
        for family, link in selected.items():
            assert is_allowed_qra_url(link.url, directly_linked_document=True)
            assert classify_document(link.anchor_text, link.url) == link.document_type
            document = http.get(link.url)
            prefix = document.content.lstrip()[:16].lower()
            assert document.content and any(prefix.startswith(signature) for signature in signatures[family])
            audit["documents"].append({
                "family": family, "document_type": link.document_type, "url": link.url,
                "http_status": document.status_code, "bytes": len(document.content),
            })
        print(json.dumps(audit, sort_keys=True))
