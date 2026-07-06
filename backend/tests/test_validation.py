from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.errors import UnsupportedQueryError
from app.schemas.query import QueryRequest, QuerySpec, QueryType
from app.validation import ensure_supported


def test_blank_query_rejected_by_schema():
    with pytest.raises(ValidationError):
        QueryRequest(query="   ")


def test_supported_query_passes_gate():
    ensure_supported(QuerySpec(query_type=QueryType.TIME_TREND))  # no raise


def test_unsupported_query_type_raises():
    spec = QuerySpec(query_type=QueryType.UNSUPPORTED, supported=False, rejection_reason="nope")
    with pytest.raises(UnsupportedQueryError):
        ensure_supported(spec)


def test_supported_false_raises_even_if_type_set():
    spec = QuerySpec(query_type=QueryType.TIME_TREND, supported=False)
    with pytest.raises(UnsupportedQueryError):
        ensure_supported(spec)
