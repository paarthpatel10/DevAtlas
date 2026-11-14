"""
SQL Prompt — prompt template for SQL query generation.
Provides schema context and self-correction feedback to the LLM.
"""

from typing import Dict, List


SQL_SYSTEM_PROMPT = """You are a SQL query generator for a PostgreSQL analytics database.

Given the database schema and a user's question, generate a SQL query that answers it.

RULES

1. Always include a LIMIT clause (max 100 rows unless the user asks for a specific count).
2. Use proper PostgreSQL syntax.
3. Use table aliases for readability.
4. Handle NULL values appropriately.
5. Use appropriate aggregate functions (COUNT, SUM, AVG, MIN, MAX) when the question asks for summaries.
6. Use JOINs when the question requires data from multiple tables.

Return ONLY the SQL query inside a ```sql code block. No explanations outside the code block.

DATABASE SCHEMA:
{schema_context}
"""


def build_sql_generation_prompt(
    user_query: str,
    schema_context: str,
    chat_history: List[Dict[str, str]] | None = None,
    previous_error: str = "",
) -> str:
    """
    Builds the full SQL generation prompt with schema context.

    Args:
        user_query: The user's natural language question.
        schema_context: Formatted database schema.
        chat_history: Optional conversation history.
        previous_error: If retrying, the error from the previous SQL attempt.
    """
    system = SQL_SYSTEM_PROMPT.format(schema_context=schema_context)

    history_text = ""
    if chat_history:
        for msg in chat_history:
            history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

    # Self-correction context: if we're retrying, show the LLM what went wrong
    error_section = ""
    if previous_error:
        error_section = f"""
═══════════════════════════════════════════════════════════════
SELF-CORRECTION: Your previous SQL query FAILED with this error:
{previous_error}

Please analyze the error carefully and generate a CORRECTED SQL query.
Common fixes: check table/column names against the schema, fix JOIN conditions,
handle type mismatches, and ensure proper GROUP BY clauses.
═══════════════════════════════════════════════════════════════
"""

    prompt = f"""{system}

Chat History:
{history_text}
{error_section}
User Question: {user_query}

SQL Query:"""
    return prompt
