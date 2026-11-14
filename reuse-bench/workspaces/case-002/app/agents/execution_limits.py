"""
Execution Limits — tool whitelist plus step and retry limits for the workflow.
"""

from typing import List

from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

ALLOWED_TOOLS: List[str] = [
    "sql_agent",
    "rag_agent",
    "router_agent",
    "response_agent",
    "schema_introspector",
    "sql_executor",
]


class ExecutionLimits:
    """Enforces tool whitelist and execution limits for the agent workflow."""

    def __init__(self) -> None:
        self.max_steps: int = settings.MAX_GRAPH_STEPS
        self.retry_limit: int = settings.RETRY_LIMIT
        self.query_timeout: int = settings.QUERY_TIMEOUT_SECONDS

    def validate_tool(self, tool_name: str) -> bool:
        """Checks whether a tool is in the allowed whitelist."""
        is_allowed = tool_name in ALLOWED_TOOLS
        if not is_allowed:
            logger.warning(f"Tool '{tool_name}' not in whitelist: {ALLOWED_TOOLS}")
        return is_allowed

    def check_step_limit(self, current_step: int) -> bool:
        """Returns True if execution is within the step limit."""
        within_limit = current_step < self.max_steps
        if not within_limit:
            logger.warning(f"Step limit reached: {current_step} >= {self.max_steps}")
        return within_limit

    def check_retry_limit(self, current_retries: int) -> bool:
        """Returns True if retries are within the limit."""
        within_limit = current_retries < self.retry_limit
        if not within_limit:
            logger.warning(f"Retry limit reached: {current_retries} >= {self.retry_limit}")
        return within_limit
