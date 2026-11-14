"""
Tracing — decorators and utilities for observability.
Provides structured tracing for graph nodes and agent calls.
"""

import functools
import time
from typing import Any, Callable, Dict

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def trace_node(node_name: str) -> Callable:
    """
    Decorator that traces a graph node function execution.
    Logs entry, exit, duration, input/output keys, and any errors.

    Usage:
        @trace_node("router")
        def router_node(state: GraphState) -> Dict[str, Any]:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(state: Dict[str, Any], *args, **kwargs) -> Dict[str, Any]:
            start_time = time.time()
            input_keys = list(state.keys()) if isinstance(state, dict) else []

            logger.info(
                f"[TRACE] Node '{node_name}' START | "
                f"Input keys: {input_keys}"
            )

            try:
                result = func(state, *args, **kwargs)

                duration = time.time() - start_time
                output_keys = (
                    list(result.keys()) if isinstance(result, dict) else []
                )

                logger.info(
                    f"[TRACE] Node '{node_name}' END | "
                    f"Duration: {duration:.3f}s | "
                    f"Output keys: {output_keys}"
                )

                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"[TRACE] Node '{node_name}' ERROR | "
                    f"Duration: {duration:.3f}s | "
                    f"Error: {e}"
                )
                raise

        return wrapper

    return decorator


def trace_agent_call(agent_name: str, action: str) -> Callable:
    """
    Decorator that traces an agent method call.

    Usage:
        @trace_agent_call("sql_agent", "run")
        def run(self, query: str) -> Dict[str, Any]:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()

            logger.info(
                f"[TRACE] Agent '{agent_name}.{action}' START"
            )

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                logger.info(
                    f"[TRACE] Agent '{agent_name}.{action}' END | "
                    f"Duration: {duration:.3f}s"
                )

                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"[TRACE] Agent '{agent_name}.{action}' ERROR | "
                    f"Duration: {duration:.3f}s | "
                    f"Error: {e}"
                )
                raise

        return wrapper

    return decorator
