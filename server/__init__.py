"""Server package for exposing HTTP APIs around the agent system."""

from .copilot_adapter import (
    CopilotBackend,
    create_copilot_router,
    get_copilot_backend,
)

__all__ = [
    "CopilotBackend",
    "create_copilot_router",
    "get_copilot_backend",
]

