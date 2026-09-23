from datetime import UTC, date, datetime
from uuid import uuid4

import httpx

from ust_pipeline.config import Settings
from ust_pipeline.fiscal import AUCTIONS_URL, FiscalPage
from ust_pipeline.pipeline import Pipeline
from ust_pipeline.qra.discovery import QraIndex, QraLink


def minimal_raw():
    return {
        "record_date": "2026-08-01", "cusip": "91282TEST", "security_type": "Note", "security_term": "2-Year",
        "auction_date": "2026-08-25", "issue_date": "2026-08-31", "maturity_date": "2028-08-31",
        "inflation_index_security": "No", "floating_rate": "No", "reopening": "No", "cash_management_bill_cmb": "No",
        "high_yield": "3.5", "offering_amt": "0",
    }


def test_partial_page_failure_keeps_completed_page(monkeypatch, tmp_path):
    class FakeFiscal:
        def __init__(self, *args, **kwargs):
            pass

        def iter_auction_pages(self, start, end):
            yield FiscalPage(1, [minimal_raw()], {"total-pages": 2}, {"next": "x"}, b"{}", "https://example.test/1", {})
            raise RuntimeError("page 2 unavailable")

    monkeypatch.setattr("ust_pipeline.pipeline.FiscalDataClient", FakeFiscal)
    settings = Settings(raw_root=tmp_path, http_max_retries=0)
    outcome = Pipeline(settings, repository=None, dry_run=True).auctions(date(2026, 8, 1), date(2026, 8, 31), "TEST")
    assert outcome.status == "PARTIAL_FAILURE"
    assert outcome.pages_succeeded == 1
    assert outcome.received == 1
    assert outcome.exit_code == 3


def test_sync_auctions_uses_overlap_and_future_announcement_window(monkeypatch, tmp_path):
    settings = Settings(raw_root=tmp_path, auction_overlap_days=37)
    pipeline = Pipeline(settings, repository=None, dry_run=True)
    captured = {}

    def fake_auctions(start, end, job_type):
        captured.update(start=start, end=end, job_type=job_type)
        from ust_pipeline.pipeline import RunOutcome
        return RunOutcome("DRY_RUN")

    monkeypatch.setattr(pipeline, "auctions", fake_auctions)
    assert pipeline.sync_auctions(date(2026, 9, 7)).exit_code == 0
    assert captured == {
        "start": date(2026, 8, 1),
        "end": date(2026, 10, 22),
        "job_type": "SYNC_AUCTIONS",
    }


def test_auction_dry_run_normalizes_without_repository_or_raw_write(monkeypatch, tmp_path):
    class FakeFiscal:
        def __init__(self, *args, **kwargs):
            pass

        def iter_auction_pages(self, start, end):
            yield FiscalPage(1, [minimal_raw()], {"total-pages": 1}, {}, b"{}", AUCTIONS_URL, {})

    monkeypatch.setattr("ust_pipeline.pipeline.FiscalDataClient", FakeFiscal)
    pipeline = Pipeline(Settings(raw_root=tmp_path, http_max_retries=0), repository=None, dry_run=True)
    monkeypatch.setattr(pipeline.raw_store, "put", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("raw write")))
    outcome = pipeline.auctions(date(2026, 8, 1), date(2026, 8, 31), "TEST_DRY_RUN")
    assert outcome.status == "DRY_RUN"
    assert (outcome.received, outcome.unchanged, outcome.rejected) == (1, 1, 0)


class AuditRepository:
    def __init__(self):
        self.run_id = uuid4()
        self.requests = []
        self.issues = []
        self.updates = []

    def start_run(self, *args):
        return self.run_id

    def update_run(self, run_id, **values):
        assert run_id == self.run_id
        self.updates.append(values)

    def save_snapshot(self, *args, **kwargs):
        return uuid4()

    def upsert_auction(self, *args, **kwargs):
        return uuid4(), "INSERTED"

    def record_request(self, run_id, url, status=None, headers=None, error=None):
        self.requests.append({"run_id": run_id, "url": url, "status": status, "headers": headers, "error": error})

    def issue(self, run_id, rule, message, **kwargs):
        self.issues.append({"run_id": run_id, "rule": rule, "message": message, **kwargs})

    def conditional_headers(self, url):
        return "saved-etag", "Wed, 05 Aug 2026 12:30:00 GMT"


def test_partial_page_failure_records_request_issue_checkpoint_and_final_counts(monkeypatch, tmp_path):
    class FakeFiscal:
        def __init__(self, *args, **kwargs):
            pass

        def iter_auction_pages(self, start, end):
            yield FiscalPage(1, [minimal_raw()], {"total-pages": 2}, {}, b"{}", AUCTIONS_URL + "?page[number]=1", {})
            raise RuntimeError("page 2 unavailable")

    monkeypatch.setattr("ust_pipeline.pipeline.FiscalDataClient", FakeFiscal)
    repository = AuditRepository()
    outcome = Pipeline(Settings(raw_root=tmp_path, http_max_retries=0), repository, dry_run=False).auctions(
        date(2026, 8, 1), date(2026, 8, 31), "TEST_PARTIAL"
    )
    assert outcome.status == "PARTIAL_FAILURE" and outcome.exit_code == 3
    assert (outcome.pages_attempted, outcome.pages_succeeded, outcome.inserted) == (2, 1, 1)
    assert repository.requests[-1]["url"] == AUCTIONS_URL
    assert repository.requests[-1]["error"] == "page 2 unavailable"
    assert repository.issues[-1]["rule"] == "AUCTION_PAGE_FAILED"
    assert repository.updates[0]["checkpoint"] == {"last_completed_page": 1, "total_pages": 2}
    assert repository.updates[-1]["status"] == "PARTIAL_FAILURE"
    assert repository.updates[-1]["pages_attempted"] == 2


def test_page_is_not_counted_successful_when_snapshot_write_fails(monkeypatch, tmp_path):
    class FakeFiscal:
        def __init__(self, *args, **kwargs):
            pass

        def iter_auction_pages(self, start, end):
            yield FiscalPage(1, [minimal_raw()], {"total-pages": 1}, {}, b"{}", AUCTIONS_URL, {})

    class SnapshotFailureRepository(AuditRepository):
        def save_snapshot(self, *args, **kwargs):
            raise RuntimeError("snapshot unavailable")

    monkeypatch.setattr("ust_pipeline.pipeline.FiscalDataClient", FakeFiscal)
    repository = SnapshotFailureRepository()
    outcome = Pipeline(Settings(raw_root=tmp_path, http_max_retries=0), repository, dry_run=False).auctions(
        date(2026, 8, 1), date(2026, 8, 31), "TEST_SNAPSHOT_FAILURE"
    )
    assert outcome.status == "FAILED" and outcome.exit_code == 1
    assert (outcome.pages_attempted, outcome.pages_succeeded) == (1, 0)
    assert repository.requests[-1]["error"] == "snapshot unavailable"
    assert repository.issues[-1]["rule"] == "AUCTION_PAGE_FAILED"


def test_qra_304_uses_conditional_headers_and_records_unchanged(monkeypatch, tmp_path):
    document_url = "https://home.treasury.gov/system/files/221/auction-calendar.xml"
    seed_link = QraLink(
        document_url,
        "Tentative Auction Schedule XML",
        "TENTATIVE_AUCTION_XML",
        "https://home.treasury.gov/qra-seed",
        datetime(2026, 8, 5, 12, 30, tzinfo=UTC),
        2026,
        3,
    )

    class FakeHttp:
        calls = []

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, *, etag=None, last_modified=None, **kwargs):
            self.calls.append((url, etag, last_modified))
            request = httpx.Request("GET", url)
            if url == document_url:
                return httpx.Response(304, request=request, headers={"etag": "saved-etag"})
            return httpx.Response(200, request=request, content=b"<html></html>", headers={"content-type": "text/html"})

    def fake_discovery(content, page_url):
        if page_url.endswith("most-recent-quarterly-refunding-documents"):
            return QraIndex([seed_link], [])
        return QraIndex([], [])

    monkeypatch.setattr("ust_pipeline.pipeline.TreasuryHttpClient", FakeHttp)
    monkeypatch.setattr("ust_pipeline.pipeline.discover_qra_index", fake_discovery)
    repository = AuditRepository()
    outcome = Pipeline(
        Settings(raw_root=tmp_path, http_max_retries=0, qra_request_delay_seconds=0), repository, dry_run=False
    ).crawl_qra(latest=True)
    assert outcome.status == "SUCCESS"
    assert (outcome.documents_attempted, outcome.documents_succeeded, outcome.unchanged) == (3, 3, 1)
    assert FakeHttp.calls[-1] == (document_url, "saved-etag", "Wed, 05 Aug 2026 12:30:00 GMT")
    assert repository.requests[-1]["status"] == 304
    assert repository.updates[-1]["documents_succeeded"] == 3


def test_qra_document_version_action_updates_distinct_run_counter(monkeypatch, tmp_path, fixture_dir):
    document_url = "https://home.treasury.gov/system/files/221/auction-calendar.xml"
    link = QraLink(
        document_url,
        "Tentative Auction Schedule XML",
        "TENTATIVE_AUCTION_XML",
        "https://home.treasury.gov/qra-seed",
        datetime(2026, 8, 5, 12, 30, tzinfo=UTC),
        2026,
        3,
    )
    xml_content = (fixture_dir / "auction_schedule_2026q3.xml").read_bytes()

    class FakeHttp:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            request = httpx.Request("GET", url)
            content = xml_content if url == document_url else b"<html></html>"
            content_type = "application/xml" if url == document_url else "text/html"
            return httpx.Response(200, request=request, content=content, headers={"content-type": content_type})

    class VersionRepository(AuditRepository):
        def __init__(self, action):
            super().__init__()
            self.action = action

        def upsert_refunding(self, *args):
            return uuid4()

        def save_qra_document(self, *args):
            return uuid4(), True, self.action

    monkeypatch.setattr("ust_pipeline.pipeline.TreasuryHttpClient", FakeHttp)
    monkeypatch.setattr(
        "ust_pipeline.pipeline.discover_qra_index",
        lambda content, page_url: QraIndex([link], [])
        if page_url.endswith("most-recent-quarterly-refunding-documents")
        else QraIndex([], []),
    )
    settings = Settings(raw_root=tmp_path, qra_request_delay_seconds=0)
    inserted = Pipeline(settings, VersionRepository("INSERTED"), dry_run=False).crawl_qra(latest=True)
    updated = Pipeline(settings, VersionRepository("UPDATED"), dry_run=False).crawl_qra(latest=True)
    assert (inserted.inserted, inserted.updated, inserted.unchanged) == (1, 0, 0)
    assert (updated.inserted, updated.updated, updated.unchanged) == (0, 1, 0)
