from argparse import Namespace
from contextlib import contextmanager
from datetime import date
import os

import pytest
from sqlalchemy import text

from ust_pipeline import cli
from ust_pipeline.config import Settings
from ust_pipeline.pipeline import RunOutcome
from ust_pipeline.repository import Repository


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["init-db", "--help"],
        ["backfill-auctions", "--help"],
        ["sync-auctions", "--help"],
        ["validate-auctions", "--help"],
        ["crawl-qra", "--help"],
        ["sync-all", "--help"],
        ["validate", "--help"],
    ],
)
def test_every_cli_help_path_exits_zero(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(argv)
    assert exc.value.code == 0
    capsys.readouterr()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["unknown"],
        ["backfill-auctions", "--from", "2026-09-02", "--to", "2026-09-01"],
        ["backfill-auctions", "--from", "bad", "--to", "2026-09-01"],
        ["crawl-qra"],
        ["crawl-qra", "--backfill-from", "1969"],
    ],
)
def test_cli_input_errors_exit_two(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(argv)
    assert exc.value.code == 2
    capsys.readouterr()


@pytest.mark.parametrize(
    ("status", "expected"),
    [("SUCCESS", 0), ("DRY_RUN", 0), ("FAILED", 1), ("PARTIAL_FAILURE", 3), ("UNKNOWN", 1)],
)
def test_pipeline_status_exit_codes(status, expected):
    assert RunOutcome(status).exit_code == expected


class FakePipeline:
    def __init__(self, settings, repository, dry_run):
        self.calls = []

    def auctions(self, start, end, job_type):
        self.calls.append(("auctions", start, end, job_type))
        return RunOutcome("SUCCESS")

    def sync_auctions(self):
        self.calls.append(("sync-auctions",))
        return RunOutcome("PARTIAL_FAILURE")

    def crawl_qra(self, *, latest=True, backfill_from=None):
        self.calls.append(("crawl-qra", latest, backfill_from))
        return RunOutcome("FAILED" if latest else "SUCCESS")


def test_dispatch_backfill_is_inclusive_and_success(monkeypatch, tmp_path, capsys):
    holder = {}

    def factory(*args):
        holder["pipeline"] = FakePipeline(*args)
        return holder["pipeline"]

    monkeypatch.setattr(cli, "Pipeline", factory)
    args = Namespace(command="backfill-auctions", start=date(2026, 8, 1), end=date(2026, 8, 31), dry_run=True)
    assert cli.dispatch(args, Settings(raw_root=tmp_path), None) == 0
    assert holder["pipeline"].calls == [("auctions", date(2026, 8, 1), date(2026, 8, 31), "BACKFILL_AUCTIONS")]
    capsys.readouterr()


def test_dispatch_sync_all_returns_most_severe_exit_code(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "Pipeline", FakePipeline)
    args = Namespace(command="sync-all", dry_run=True)
    assert cli.dispatch(args, Settings(raw_root=tmp_path), None) == 3
    capsys.readouterr()


def test_dispatch_qra_latest_and_backfill_modes(monkeypatch, tmp_path, capsys):
    created = []

    def factory(*args):
        created.append(FakePipeline(*args))
        return created[-1]

    monkeypatch.setattr(cli, "Pipeline", factory)
    latest = Namespace(command="crawl-qra", dry_run=True, latest=True, backfill_from=None)
    backfill = Namespace(command="crawl-qra", dry_run=True, latest=False, backfill_from=2020)
    assert cli.dispatch(latest, Settings(raw_root=tmp_path), None) == 1
    assert cli.dispatch(backfill, Settings(raw_root=tmp_path), None) == 0
    assert created[0].calls == [("crawl-qra", True, None)]
    assert created[1].calls == [("crawl-qra", False, 2020)]
    capsys.readouterr()


def test_validate_auction_scope_and_full_scope_exit_codes(capsys):
    class FakeRepository:
        calls = []

        def validation_report(self, *, auction_only=False):
            self.calls.append(auction_only)
            return {"problem": 0 if auction_only else 1}

    repository = FakeRepository()
    assert cli.dispatch(Namespace(command="validate-auctions", dry_run=False), Settings(), repository) == 0
    assert cli.dispatch(Namespace(command="validate", dry_run=False), Settings(), repository) == 2
    assert repository.calls == [True, False]
    capsys.readouterr()


def test_init_db_calls_alembic_head_and_dry_run_is_noop(monkeypatch, capsys):
    from alembic import command

    calls = []
    monkeypatch.setattr(command, "upgrade", lambda config, revision: calls.append(revision))
    assert cli.dispatch(Namespace(command="init-db", dry_run=True), Settings(), None) == 0
    assert calls == []
    assert cli.dispatch(Namespace(command="init-db", dry_run=False), Settings(), object()) == 0
    assert calls == ["head"]
    capsys.readouterr()


def test_main_dry_run_never_constructs_repository(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Repository", lambda *args: pytest.fail("dry-run constructed Repository"))
    monkeypatch.setattr(cli, "dispatch", lambda args, settings, repository: 0 if repository is None else 1)
    assert cli.main(["validate", "--dry-run"]) == 0
    capsys.readouterr()


def test_main_lock_contention_returns_failed_exit_code(monkeypatch, capsys):
    class LockedRepository:
        @contextmanager
        def job_lock(self):
            raise RuntimeError("another UST ingestion command is running")
            yield

    monkeypatch.setattr(cli, "Repository", lambda *args: LockedRepository())
    assert cli.main(["validate"]) == 1
    assert '"status": "FAILED"' in capsys.readouterr().out


@pytest.mark.integration
def test_postgresql_advisory_lock_serializes_collectors():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL must point to a disposable PostgreSQL 16 DB")
    first = Repository(url)
    second = Repository(url)
    try:
        with first.job_lock():
            with second.engine.connect() as connection:
                assert connection.execute(text("SELECT pg_try_advisory_lock(hashtext('ust_pipeline_ingestion'))")).scalar_one() is False
        with second.engine.connect() as connection:
            assert connection.execute(text("SELECT pg_try_advisory_lock(hashtext('ust_pipeline_ingestion'))")).scalar_one() is True
            assert connection.execute(text("SELECT pg_advisory_unlock(hashtext('ust_pipeline_ingestion'))")).scalar_one() is True
    finally:
        first.engine.dispose()
        second.engine.dispose()
