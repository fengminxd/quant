"""Supabase PostgreSQL schema initialization."""

from __future__ import annotations

from pathlib import Path

from data.market_config import SupabaseConfig


DEFAULT_SCHEMA_PATH = Path("data/schema.sql")


def create_schema(
    config: SupabaseConfig,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> None:
    """Create the required OHLCV table and indexes through PostgreSQL."""

    if not config.db_url:
        raise ValueError("db_url is required to create Supabase tables")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("install psycopg[binary] to create Supabase tables") from exc

    sql = Path(schema_path).read_text(encoding="utf-8")
    with psycopg.connect(config.db_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
        connection.commit()
