from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .config import Settings
from .logging import configure_logging
from .pipeline import Pipeline
from .repository import Repository


ROOT = Path(__file__).resolve().parents[2]
DDL_PATH = ROOT / "db" / "ust_pipeline_schema.sql"


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def refunding_year(value: str) -> int:
    try:
        year = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a four-digit year") from exc
    if not 1970 <= year <= 2200:
        raise argparse.ArgumentTypeError("year must be between 1970 and 2200")
    return year


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="fetch and validate without raw or database writes")
    common.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS, help="enable debug structured logs")
    parser = argparse.ArgumentParser(prog="ust-data", description="UST auction and QRA data pipeline", parents=[common])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", parents=[common], add_help=True)
    backfill = commands.add_parser("backfill-auctions", parents=[common], add_help=True)
    backfill.add_argument("--from", dest="start", type=iso_date, required=True)
    backfill.add_argument("--to", dest="end", type=iso_date, required=True)
    commands.add_parser("sync-auctions", parents=[common], add_help=True)
    commands.add_parser("validate-auctions", parents=[common], add_help=True)
    crawl = commands.add_parser("crawl-qra", parents=[common], add_help=True)
    group = crawl.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true")
    group.add_argument("--backfill-from", type=refunding_year, metavar="YEAR")
    commands.add_parser("sync-all", parents=[common], add_help=True)
    commands.add_parser("validate", parents=[common], add_help=True)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "backfill-auctions" and args.start > args.end:
        parser.error("--from must be on or before --to")
    args.dry_run = getattr(args, "dry_run", False)
    args.verbose = getattr(args, "verbose", False)
    return args


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, default=str, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level, args.verbose)
    repository = None if args.dry_run else Repository(settings.database_url)
    try:
        if repository:
            with repository.job_lock():
                return dispatch(args, settings, repository)
        return dispatch(args, settings, repository)
    except Exception as exc:
        emit({"status": "FAILED", "error_type": type(exc).__name__, "message": "Command failed; check connection/configuration and ingestion_run / structured logs."})
        return 1


def dispatch(args, settings, repository):
    if args.command == "init-db":
        if args.dry_run:
            emit({"status": "DRY_RUN", "ddl": str(DDL_PATH), "bytes": DDL_PATH.stat().st_size})
            return 0
        from alembic import command
        from alembic.config import Config
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        emit({"status": "SUCCESS", "schema": "ust", "ddl": str(DDL_PATH)})
        return 0
    if args.command in {"validate", "validate-auctions"}:
        if args.dry_run:
            emit({"status": "DRY_RUN", "checks": "database validation skipped"})
            return 0
        report = repository.validation_report(auction_only=args.command == "validate-auctions")
        emit({"status": "SUCCESS" if not any(report.values()) else "FAILED", "checks": report})
        return 0 if not any(report.values()) else 2
    pipeline = Pipeline(settings, repository, args.dry_run)
    if args.command == "backfill-auctions":
        outcome = pipeline.auctions(args.start, args.end, "BACKFILL_AUCTIONS")
    elif args.command == "sync-auctions":
        outcome = pipeline.sync_auctions()
    elif args.command == "crawl-qra":
        outcome = pipeline.crawl_qra(latest=args.latest, backfill_from=args.backfill_from)
    elif args.command == "sync-all":
        auction = pipeline.sync_auctions()
        qra = pipeline.crawl_qra(latest=True)
        emit({"auctions": asdict(auction), "qra": asdict(qra)})
        return max(auction.exit_code, qra.exit_code)
    else:
        raise AssertionError(args.command)
    emit(asdict(outcome))
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
