"""Layer-2 capability gate.

Layer 1 (request-schema validation) is enforced by `QueryRequest` / FastAPI.
Layer 2 is semantic: after the LLM classifies the query, reject anything that
falls outside the closed taxonomy *before* any external fetch or DB write.
"""

from __future__ import annotations

from .errors import UnsupportedQueryError
from .schemas.query import QuerySpec, QueryType


def ensure_supported(spec: QuerySpec) -> None:
    """Raise UnsupportedQueryError (-> HTTP 422) if the query isn't answerable."""
    if spec.query_type == QueryType.UNSUPPORTED or not spec.supported:
        raise UnsupportedQueryError(spec.rejection_reason)
