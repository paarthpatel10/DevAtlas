"""
SQL Executor — executes SQL queries against PostgreSQL.
"""

from typing import Any, Dict, List

from sqlalchemy import text

from app.config.settings import settings
from app.database.postgres import get_engine
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class SQLExecutor:
    """Executes SQL queries against the analytics database."""

    def __init__(self) -> None:
        self.engine = get_engine()
        self.timeout_seconds = settings.QUERY_TIMEOUT_SECONDS

    def execute(self, sql_query: str) -> Dict[str, Any]:
        """
        Executes a SQL query.

        Returns:
            dict with keys:
                - success (bool): whether the query executed successfully
                - columns (list[str]): column names from the result
                - rows (list[dict]): result rows as dicts
                - row_count (int): number of rows returned
                - error (str | None): error message if execution failed
        """
        # Execute with timeout
        logger.info(f"Executing SQL query: {sql_query[:100]}...")
        try:
            with self.engine.connect() as conn:
                # Set statement timeout
                conn.execute(
                    text(f"SET statement_timeout = '{self.timeout_seconds * 1000}'")
                )

                result = conn.execute(text(sql_query))

                # Extract column names and rows
                columns = list(result.keys()) if result.returns_rows else []
                rows = [dict(zip(columns, row)) for row in result.fetchall()] if result.returns_rows else []

                logger.info(f"Query returned {len(rows)} rows")
                return {
                    "success": True,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "error": None,
                }

        except Exception as e:
            logger.error(f"Error executing SQL query: {e}")
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": f"Query execution failed: {str(e)}",
            }

    def format_results_as_text(self, result: Dict[str, Any]) -> str:
        """Formats SQL execution results as a readable text block for LLM consumption."""
        if not result["success"]:
            return f"Error: {result['error']}"

        if result["row_count"] == 0:
            return "Query executed successfully but returned no rows."

        # Build a text table
        columns = result["columns"]
        rows = result["rows"]

        # Header
        header = " | ".join(str(col) for col in columns)
        separator = "-" * len(header)
        lines = [header, separator]

        # Rows (limit to 50 for prompt size)
        display_rows = rows[:50]
        for row in display_rows:
            line = " | ".join(str(row.get(col, "")) for col in columns)
            lines.append(line)

        if len(rows) > 50:
            lines.append(f"... and {len(rows) - 50} more rows")

        lines.append(f"\nTotal rows: {result['row_count']}")
        return "\n".join(lines)
