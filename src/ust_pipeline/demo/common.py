from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url


DEMO_ENV = "UST_DEMO_DATABASE_URL"
PRODUCTION_ENV = "UST_DATABASE_URL"
MIGRATION_HEAD = "20260903_0001"


class DemoSafetyError(RuntimeError):
    """The requested target is outside the demo database safety boundary."""


class ValidationFailure(RuntimeError):
    """The demo load or export completed work but failed a contract check."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def canonical_url(value: str) -> URL:
    try:
        url = make_url(value)
    except Exception as exc:  # pragma: no cover - SQLAlchemy supplies the detail
        raise DemoSafetyError(f"invalid PostgreSQL URL: {exc}") from exc
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise DemoSafetyError("UST_DEMO_DATABASE_URL must use PostgreSQL/psycopg")
    database = (url.database or "").lower()
    if "demo" not in database and "test" not in database:
        raise DemoSafetyError("demo database name must contain 'demo' or 'test'")
    return url


def urls_equal(left: str, right: str) -> bool:
    return make_url(left) == make_url(right)


def demo_database_url(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    value = env.get(DEMO_ENV)
    if not value:
        raise DemoSafetyError(f"{DEMO_ENV} is required")
    canonical_url(value)
    production = env.get(PRODUCTION_ENV)
    if production and urls_equal(value, production):
        raise DemoSafetyError(f"{DEMO_ENV} must not equal {PRODUCTION_ENV}")
    return value


def database_name(value: str) -> str:
    return canonical_url(value).database or ""


def redacted_database_url(value: str) -> str:
    url = canonical_url(value)
    return str(url.set(password="***" if url.password else None))


def create_demo_engine(value: str) -> Engine:
    return create_engine(value, pool_pre_ping=True, hide_parameters=True)


def ddl_objects(root: Path | None = None) -> tuple[set[str], set[str]]:
    ddl = (root or repository_root()) / "db" / "ust_pipeline_schema.sql"
    sql = ddl.read_text(encoding="utf-8")
    tables = set(re.findall(r"(?im)^CREATE\s+TABLE\s+ust\.([a-z0-9_]+)", sql))
    views = set(re.findall(r"(?im)^CREATE\s+VIEW\s+ust\.([a-z0-9_]+)", sql))
    return tables, views


def catalog_objects(engine: Engine) -> tuple[list[str], list[str]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema='ust'
            ORDER BY table_name
        """)).all()
    tables = [name for name, kind in rows if kind == "BASE TABLE"]
    views = [name for name, kind in rows if kind == "VIEW"]
    return tables, views


def server_info(engine: Engine) -> dict[str, str | int]:
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT current_database(), current_setting('server_version'), current_setting('server_version_num')::int"
        )).one()
    if int(row[2]) < 160000:
        raise DemoSafetyError("PostgreSQL 16 or newer is required")
    return {"database": row[0], "server_version": row[1], "server_version_num": int(row[2])}


def _user_relations(engine: Engine) -> set[tuple[str, str, str]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT n.nspname, c.relname, c.relkind
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind IN ('r','p','v','m')
              AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND n.nspname NOT LIKE 'pg_toast%'
              AND NOT (n.nspname='public' AND c.relname='alembic_version')
            ORDER BY 1,2
        """)).all()
    return {(schema, name, kind) for schema, name, kind in rows}


def _has_demo_marker(engine: Engine) -> bool:
    with engine.connect() as connection:
        exists = connection.execute(text("SELECT to_regclass('ust.ingestion_run') IS NOT NULL")).scalar_one()
        if not exists:
            return False
        return bool(connection.execute(text(
            "SELECT EXISTS(SELECT 1 FROM ust.ingestion_run WHERE source_name='DEMO_FIXTURE')"
        )).scalar_one())


def _is_pristine_migrated_schema(engine: Engine, expected_tables: set[str]) -> bool:
    tables, views = catalog_objects(engine)
    _, expected_views = ddl_objects()
    if set(tables) != expected_tables or set(views) != expected_views:
        return False
    with engine.connect() as connection:
        for table in tables:
            count = int(connection.execute(text(f'SELECT count(*) FROM ust."{table}"')).scalar_one())
            allowed = 1 if table == "derived_metric_method" else 7 if table == "derived_metric_method_parameter" else 0
            if count != allowed:
                return False
    return True


def assert_safe_database_state(engine: Engine, *, allow_empty: bool = True) -> str:
    info = server_info(engine)
    name = str(info["database"]).lower()
    if "demo" not in name and "test" not in name:
        raise DemoSafetyError("connected database name must contain 'demo' or 'test'")
    relations = _user_relations(engine)
    if not relations:
        if allow_empty:
            return "EMPTY"
        raise DemoSafetyError("demo database has not been migrated")
    expected_tables, expected_views = ddl_objects()
    expected_relations = {("ust", item, "r") for item in expected_tables} | {
        ("ust", item, "v") for item in expected_views
    }
    if relations != expected_relations:
        raise DemoSafetyError("non-empty database contains unrecognized relations")
    if _has_demo_marker(engine):
        return "DEMO_FIXTURE"
    if _is_pristine_migrated_schema(engine, expected_tables):
        return "MIGRATED_EMPTY"
    raise DemoSafetyError("non-empty database is not an identified DEMO_FIXTURE database")


@contextmanager
def _alembic_demo_environment(database_url: str) -> Iterator[None]:
    # Existing Alembic env.py reads Settings().database_url. The public input
    # remains UST_DEMO_DATABASE_URL; this process-local bridge is restored.
    sentinel = object()
    previous: str | object = os.environ.get(PRODUCTION_ENV, sentinel)
    os.environ[PRODUCTION_ENV] = database_url
    try:
        yield
    finally:
        if previous is sentinel:
            os.environ.pop(PRODUCTION_ENV, None)
        else:
            os.environ[PRODUCTION_ENV] = str(previous)


def upgrade_head(database_url: str, root: Path | None = None) -> None:
    root = root or repository_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "db" / "migrations"))
    with _alembic_demo_environment(database_url):
        command.upgrade(config, "head")


def migration_version(engine: Engine) -> str | None:
    with engine.connect() as connection:
        exists = connection.execute(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")).scalar_one()
        if not exists:
            return None
        return connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one_or_none()
