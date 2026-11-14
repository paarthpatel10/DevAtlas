"""
LangSmith Client — configures and initializes LangSmith tracing.
Reads configuration from environment variables and sets up the tracing client.
"""

import os
from typing import Optional

from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def configure_langsmith() -> None:
    """
    Configures LangSmith tracing by setting the required environment variables.
    Call this at application startup before any LangChain calls.
    """
    if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
        logger.info(
            f"LangSmith tracing ENABLED for project: {settings.LANGSMITH_PROJECT}"
        )
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        if not settings.LANGSMITH_TRACING:
            logger.info("LangSmith tracing DISABLED (LANGSMITH_TRACING=false)")
        elif not settings.LANGSMITH_API_KEY:
            logger.warning(
                "LangSmith tracing DISABLED (LANGSMITH_API_KEY not set)"
            )


def get_langsmith_client() -> Optional[object]:
    """
    Returns a LangSmith client instance if tracing is enabled and configured.
    Returns None if LangSmith is not available or not configured.
    """
    if not settings.LANGSMITH_TRACING or not settings.LANGSMITH_API_KEY:
        return None

    try:
        from langsmith import Client

        client = Client(
            api_key=settings.LANGSMITH_API_KEY,
        )
        logger.info("LangSmith client initialized successfully")
        return client
    except ImportError:
        logger.warning("langsmith package not installed — tracing unavailable")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize LangSmith client: {e}")
        return None
