"""Domain exceptions."""

from __future__ import annotations


class UnsupportedQueryError(Exception):
    """Raised when a query falls outside the closed set of supported query types.

    Surfaced to the API as HTTP 422 with the list of supported query types.
    """

    def __init__(self, reason: str | None = None, event_id: str | None = None) -> None:
        self.reason = reason
        self.event_id = event_id  # set once the rejected query is persisted as an event
        super().__init__(reason or "Unsupported query")


class UpstreamError(Exception):
    """Raised when the ClinicalTrials.gov API cannot be reached or returns an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AgentError(Exception):
    """Raised when the LLM/agent interpretation step fails (e.g. bad key, rate limit)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
