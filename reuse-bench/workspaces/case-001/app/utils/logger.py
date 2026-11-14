"""
Structured logging utility for the Analytics Copilot application.
Reused from Milestone 2 with consistent formatting.
"""

import logging
import os
import sys


def setup_logger(name: str) -> logging.Logger:
    """Sets up a standardized logger for the application."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, log_level, logging.INFO)
        logger.setLevel(level)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger
