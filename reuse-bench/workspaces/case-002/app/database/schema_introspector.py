"""
Schema Introspector — reads PostgreSQL table/column metadata from information_schema.
Provides structured schema context for SQL generation prompts.
"""

from typing import Any, Dict, List

from sqlalchemy import text

from app.database.postgres import get_engine
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Module-level schema cache
_schema_cache: List[Dict[str, Any]] | None = None


class SchemaIntrospector:
    """Introspects PostgreSQL database schema for use in SQL generation prompts."""

    def __init__(self) -> None:
        self.engine = get_engine()

    def get_tables(self) -> List[str]:
        """Returns a list of user-defined table names in the public schema."""
        query = text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        with self.engine.connect() as conn:
            result = conn.execute(query)
            tables = [row[0] for row in result]
        logger.info(f"Found {len(tables)} tables in public schema")
        return tables

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Returns column metadata for a given table."""
        query = text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            ORDER BY ordinal_position;
        """)
        with self.engine.connect() as conn:
            result = conn.execute(query, {"table_name": table_name})
            columns = [
                {
                    "column_name": row[0],
                    "data_type": row[1],
                    "is_nullable": row[2],
                    "column_default": row[3],
                }
                for row in result
            ]
        return columns

    def get_full_schema(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Returns complete schema metadata for all tables.
        Results are cached after the first call unless use_cache=False.
        """
        global _schema_cache

        if use_cache and _schema_cache is not None:
            logger.info("Returning cached schema metadata")
            return _schema_cache

        logger.info("Introspecting full database schema")
        tables = self.get_tables()
        schema: List[Dict[str, Any]] = []

        for table_name in tables:
            columns = self.get_columns(table_name)
            schema.append({"table_name": table_name, "columns": columns})

        _schema_cache = schema
        logger.info(f"Schema introspection complete: {len(schema)} tables")
        return schema

    def format_schema_for_prompt(self, use_cache: bool = True) -> str:
        """
        Formats the database schema into a human-readable string
        suitable for inclusion in an LLM prompt.
        """
        schema = self.get_full_schema(use_cache=use_cache)
        parts: List[str] = []

        for table_info in schema:
            table_name = table_info["table_name"]
            columns_str = []
            for col in table_info["columns"]:
                nullable = "NULL" if col["is_nullable"] == "YES" else "NOT NULL"
                columns_str.append(
                    f"    {col['column_name']} {col['data_type']} {nullable}"
                )

            table_ddl = f"TABLE {table_name} (\n" + ",\n".join(columns_str) + "\n)"
            parts.append(table_ddl)

        return "\n\n".join(parts)

    @staticmethod
    def clear_cache() -> None:
        """Clears the schema cache, forcing a fresh introspection on next call."""
        global _schema_cache
        _schema_cache = None
        logger.info("Schema cache cleared")
