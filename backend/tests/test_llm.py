from __future__ import annotations

from types import SimpleNamespace

import httpx
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.agent.llm import (
    OpenAIModel,
    _is_retryable,
    _with_fallback,
    build_agent,
    model_list,
    resolve_model,
    run_structured,
)
from app.schemas.query import QuerySpec, QueryType


class _Transient(Exception):
    status_code = 503


def test_is_retryable_only_for_transient_conditions():
    class _HTTP(Exception):
        def __init__(self, status):
            self.status_code = status

    assert _is_retryable(_HTTP(429)) is True
    assert _is_retryable(_HTTP(503)) is True
    assert _is_retryable(httpx.ConnectTimeout("slow")) is True
    # auth / bad-request / output validation are NOT retried
    assert _is_retryable(_HTTP(401)) is False
    assert _is_retryable(_HTTP(400)) is False
    assert _is_retryable(ValueError("validation error")) is False


class _Agent:
    """Fake agent whose run() raises `err` up to `fail_times`, then returns `output`."""

    def __init__(self, err: Exception | None, fail_times: int = 0, output: str = "ok"):
        self.err, self.fail_times, self.output, self.calls = err, fail_times, output, 0

    async def run(self, _prompt: str):
        self.calls += 1
        if self.err and self.calls <= self.fail_times:
            raise self.err
        return SimpleNamespace(output=self.output)


async def test_with_fallback_retries_transient_then_succeeds():
    agent = _Agent(_Transient(), fail_times=2)  # fails twice, succeeds on the 3rd attempt
    out = await _with_fallback(lambda _m: agent, "p", ["m1"], retries_per_model=2, name="t")
    assert out == "ok"
    assert agent.calls == 3  # retried the transient failure


async def test_with_fallback_does_not_retry_nonretryable_but_tries_next_model():
    a1 = _Agent(RuntimeError("bad api key"), fail_times=99)  # non-retryable, always fails
    a2 = _Agent(None, output="recovered")
    agents = iter([a1, a2])
    out = await _with_fallback(lambda _m: next(agents), "p", ["m1", "m2"], retries_per_model=2, name="t")
    assert out == "recovered"
    assert a1.calls == 1  # not retried on the same model...
    assert a2.calls == 1  # ...but the chain still falls through to the next model


def test_openai_model_ids():
    assert OpenAIModel.GPT_4O_MINI.value == "gpt-4o-mini"
    assert OpenAIModel.GPT_4O_MINI.model_id == "openai:gpt-4o-mini"


def test_resolve_model_accepts_enum_bare_and_qualified():
    assert resolve_model(OpenAIModel.GPT_4O) == "openai:gpt-4o"
    assert resolve_model("gpt-4.1") == "openai:gpt-4.1"
    assert resolve_model("anthropic:claude-3-5-sonnet") == "anthropic:claude-3-5-sonnet"


def test_resolve_model_defaults_to_settings():
    # Falls back to the configured default when nothing is passed.
    from app.config import settings

    assert resolve_model() == f"openai:{settings.openai_model}"


def test_model_list_normalizes():
    assert model_list(None) == [None]
    assert model_list("gpt-4o") == ["gpt-4o"]
    assert model_list(OpenAIModel.GPT_4O) == [OpenAIModel.GPT_4O]
    assert model_list(["gpt-4o", "gpt-4o-mini"]) == ["gpt-4o", "gpt-4o-mini"]


async def test_run_structured_with_test_model():
    # Passing a pre-built model object (TestModel) means no real LLM/network call.
    agent = build_agent(QuerySpec, model=TestModel(), system_prompt="classify")
    spec = await run_structured("trials per year", QuerySpec, agent=agent)
    assert isinstance(spec, QuerySpec)
    assert isinstance(spec.query_type, QueryType)


async def test_run_structured_falls_back_to_next_model_on_failure():
    def boom(_messages, _info):
        raise RuntimeError("primary model down")

    failing = FunctionModel(boom)
    # First model raises (no retries), so the chain falls through to a working TestModel.
    spec = await run_structured(
        "trials per year", QuerySpec, models=[failing, TestModel()], retries_per_model=0
    )
    assert isinstance(spec, QuerySpec)
