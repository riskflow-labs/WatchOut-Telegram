from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import Boolean, DateTime, create_engine, inspect, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app import models as _models  # noqa: F401


TABLE_ORDER = [
    "users",
    "telegram_accounts",
    "telegram_login_flows",
    "telegram_targets",
    "monitor_rules",
    "telegram_messages",
    "crawl_errors",
    "rule_hits",
    "notification_channels",
    "notification_deliveries",
    "monitor_runs",
    "app_settings",
]


def _table_columns(engine, table: str) -> list[str]:
    inspector = inspect(engine)
    return [column["name"] for column in inspector.get_columns(table)]


def _target_column_types(engine, table: str) -> dict[str, object]:
    inspector = inspect(engine)
    return {column["name"]: column["type"] for column in inspector.get_columns(table)}


def _coerce_row(row: dict[str, object], column_types: dict[str, object]) -> dict[str, object]:
    coerced = dict(row)
    for column, column_type in column_types.items():
        value = coerced.get(column)
        if value is None:
            continue
        if isinstance(column_type, Boolean):
            coerced[column] = bool(value)
        elif isinstance(column_type, DateTime) and isinstance(value, str):
            try:
                coerced[column] = datetime.fromisoformat(value)
            except ValueError:
                pass
    return coerced


def _copy_table(source, src_session: Session, dst_session: Session, table: str) -> int:
    columns = _table_columns(source, table)
    if not columns:
        return 0
    rows = src_session.execute(text(f'SELECT {", ".join(columns)} FROM "{table}"')).mappings().all()
    if not rows:
        return 0
    placeholders = ", ".join(f":{column}" for column in columns)
    column_list = ", ".join(f'"{column}"' for column in columns)
    statement = text(f'INSERT INTO "{table}" ({column_list}) VALUES ({placeholders})')
    column_types = _target_column_types(dst_session.bind, table)
    dst_session.execute(statement, [_coerce_row(dict(row), column_types) for row in rows])
    return len(rows)


def _reset_postgres_sequences(session: Session, tables: Iterable[str]) -> None:
    for table in tables:
        if "id" not in _table_columns(session.bind, table):
            continue
        result = session.execute(text("SELECT pg_get_serial_sequence(:table, 'id')"), {"table": table}).scalar()
        if not result:
            continue
        session.execute(
            text(f"SELECT setval(:sequence, COALESCE((SELECT MAX(id) FROM \"{table}\"), 1), true)"),
            {"sequence": result},
        )
    session.commit()


def migrate(source_url: str, target_url: str) -> None:
    source = create_engine(source_url)
    target = create_engine(target_url)
    Base.metadata.create_all(bind=target)
    src_session = Session(bind=source)
    dst_session = Session(bind=target)
    try:
        total = 0
        for table in TABLE_ORDER:
            if table not in inspect(source).get_table_names():
                continue
            copied = _copy_table(source, src_session, dst_session, table)
            dst_session.commit()
            total += copied
            print(f"{table}: {copied}")
        _reset_postgres_sequences(dst_session, TABLE_ORDER)
        print(f"migrated_rows: {total}")
    finally:
        src_session.close()
        dst_session.close()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate SQLite data into PostgreSQL.")
    parser.add_argument("--source", required=True, help="sqlite:///... database url")
    parser.add_argument("--target", required=True, help="postgresql+psycopg:///... database url")
    args = parser.parse_args(list(argv) if argv is not None else None)
    migrate(args.source, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
