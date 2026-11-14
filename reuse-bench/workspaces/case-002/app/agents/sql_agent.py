"""
SQL Agent — handles analytics/database queries by introspecting the schema,
generating SQL, executing it, and formatting results.
"""

from typing import Any, Dict

from app.database.schema_introspector import SchemaIntrospector
from app.database.sql_executor import SQLExecutor
from app.prompts.sql_prompt import build_sql_generation_prompt
from app.rag.generator import LLMGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class SQLAgent:
    """Generates and executes SQL queries for analytics questions."""

    def __init__(self) -> None:
        self.introspector = SchemaIntrospector()
        self.executor = SQLExecutor()
        self.llm = LLMGenerator()

    def run(self, query: str, chat_history: list | None = None, previous_error: str = "") -> Dict[str, Any]:
        """
        Processes an analytics query end-to-end:
        1. Introspect schema
        2. Generate SQL via LLM (with previous error context if retrying)
        3. Execute query
        4. Return structured results

        Args:
            query: The user's natural language question.
            chat_history: Optional conversation history.
            previous_error: If retrying, the error from the last attempt.

        Returns:
            dict with keys: sql_query, result, formatted_result, success, error
        """
        if previous_error:
            logger.info(f"SQL Agent RETRYING query (previous error: {previous_error[:100]})")
        else:
            logger.info(f"SQL Agent processing query: {query[:80]}...")

        try:
            # Step 1: Get schema context
            schema_text = self.introspector.format_schema_for_prompt()
            logger.info("Schema context loaded for SQL generation")

            # Check if this is a schema conceptual query
            if self._is_schema_query(query):
                logger.info("Conceptual/Schema query detected — generating metadata explanation")
                explanation = self._handle_schema_query(query, schema_text)
                return {
                    "sql_query": None,
                    "result": {"conceptual": True},
                    "formatted_result": explanation,
                    "success": True,
                    "error": None,
                }

            # Step 2: Generate SQL via LLM
            prompt = build_sql_generation_prompt(
                user_query=query,
                schema_context=schema_text,
                chat_history=chat_history or [],
                previous_error=previous_error,
            )
            raw_response = self.llm.invoke_with_prompt(prompt)

            sql_query = self._extract_sql(raw_response)

            if not sql_query:
                return {
                    "sql_query": None,
                    "result": None,
                    "formatted_result": "I could not generate a valid SQL query for this question.",
                    "success": False,
                    "error": "SQL extraction failed from LLM response",
                }

            logger.info(f"Generated SQL: {sql_query}")

            # Step 3: Execute
            result = self.executor.execute(sql_query)

            # Step 4: Format results
            formatted = self.executor.format_results_as_text(result)

            return {
                "sql_query": sql_query,
                "result": result,
                "formatted_result": formatted,
                "success": result["success"],
                "error": result.get("error"),
            }

        except Exception as e:
            logger.error(f"SQL Agent error: {e}", exc_info=True)
            return {
                "sql_query": None,
                "result": None,
                "formatted_result": f"An error occurred while processing the query: {str(e)}",
                "success": False,
                "error": str(e),
            }

    @staticmethod
    def _extract_sql(llm_response: str) -> str | None:
        """
        Extracts the SQL query from the LLM response.
        Supports ```sql ... ``` code blocks and plain SQL.
        """
        response = llm_response.strip()

        # Try to extract from code block
        if "```sql" in response:
            parts = response.split("```sql")
            if len(parts) > 1:
                sql_part = parts[1].split("```")[0].strip()
                return sql_part

        if "```" in response:
            parts = response.split("```")
            if len(parts) >= 3:
                sql_part = parts[1].strip()
                return sql_part

        # If the response looks like SQL itself, return it
        first_word = response.split()[0].upper() if response.split() else ""
        if first_word in ("SELECT", "WITH"):
            return response

        return None

    def _is_schema_query(self, query: str) -> bool:
        """Determines if the query is conceptual or requesting schema definitions."""
        prompt = f"""Determine if the user query is asking conceptually about database tables, schema, structure, columns, table meaning, metadata, or table descriptions (e.g., "what is customer?", "describe products", "what tables are in the database?", "what does orders table contain?").
Answer with exactly "YES" or "NO". Do not provide any other text.

Query: {query}
Schema Query:"""
        try:
            resp = self.llm.invoke_with_prompt(prompt).strip().upper()
            return "YES" in resp
        except Exception:
            return False

    def _handle_schema_query(self, query: str, schema_context: str) -> str:
        """Explains the schema/metadata conceptually instead of running SQL."""
        prompt = f"""You are a database architect explaining the schema metadata to a business user.
Provide a clear, human-readable summary of the requested table, schema, columns, or metadata description. Do NOT generate or run SQL. Explain what the table contains, its key fields, and how it relates to other tables.

User Question: {query}

Database Schema:
{schema_context}

Explanation:"""
        try:
            return self.llm.invoke_with_prompt(prompt).strip()
        except Exception as e:
            return f"Unable to explain schema: {e}"

