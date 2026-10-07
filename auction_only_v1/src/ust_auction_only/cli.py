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

ROOT = Path(__file__).resolve().parents[3]
DDL_PATH = ROOT / "auction_only_v1" / "db" / "auction_schema.sql"


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ust-auction-only", description="Fiscal Data auction ingestion")
    parser.add_argument("--dry-run", action="store_true", help="fetch and validate without database writes")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    backfill = commands.add_parser("backfill-auctions")
    backfill.add_argument("--from", dest="start", type=iso_date, required=True)
    backfill.add_argument("--to", dest="end", type=iso_date, required=True)
    commands.add_parser("sync-auctions")
    commands.add_parser("validate-auctions")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "backfill-auctions" and args.start > args.end:
        parser.error("--from must be on or before --to")
    settings = Settings()
    configure_logging(settings.log_level, args.verbose)
    repository = None if args.dry_run else Repository(settings.database_url)
    try:
        if args.command == "init-db":
            if repository:
                with repository.job_lock():
                    repository.init_schema(DDL_PATH)
            print(json.dumps({"status": "DRY_RUN" if args.dry_run else "SUCCESS", "ddl": str(DDL_PATH)}))
            return 0
        if args.command == "validate-auctions":
            if args.dry_run:
                print(json.dumps({"status": "DRY_RUN"}))
                return 0
            with repository.job_lock():
                report = repository.validation_report()
            print(json.dumps({"status": "SUCCESS" if not any(report.values()) else "FAILED", "checks": report}))
            return 0 if not any(report.values()) else 2
        pipeline = Pipeline(settings, repository, args.dry_run)
        if repository:
            with repository.job_lock():
                outcome = pipeline.auctions(args.start, args.end, "BACKFILL_AUCTIONS") if args.command == "backfill-auctions" else pipeline.sync_auctions()
        else:
            outcome = pipeline.auctions(args.start, args.end, "BACKFILL_AUCTIONS") if args.command == "backfill-auctions" else pipeline.sync_auctions()
        print(json.dumps(asdict(outcome), ensure_ascii=False, default=str))
        return outcome.exit_code
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
