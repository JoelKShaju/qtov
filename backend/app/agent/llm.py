"""Model-agnostic LLM helper.

Everything that talks to an LLM goes through here, so callers never touch
pydantic-ai's model classes or worry about its cross-version API drift. Swapping
models is a one-line change (an `OpenAIModel` enum member, a bare name, or a
fully-qualified ``provider:model`` string).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import Enum
from typing import Any, TypeVar

import httpx
import structlog
from pydantic import BaseModel
from pydantic_ai import Agent

OutputT = TypeVar("OutputT", bound=BaseModel)

# structlog directly (not app.observability.logging) to avoid a config<->llm import cycle.
log = structlog.get_logger(__name__)

# HTTP statuses worth another attempt against the same model; everything else (auth 401/403,
# bad-request 400, output ValidationError, etc.) is not recoverable by retrying.
_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def _is_retryable(err: Exception) -> bool:
    """True only for transient upstream conditions (rate limits, 5xx, network blips)."""
    status = getattr(err, "status_code", None)
    if isinstance(status, int):
        return status in _RETRYABLE_STATUS
    return isinstance(err, (httpx.TimeoutException, httpx.TransportError))


class OpenAIModel(str, Enum):
    """OpenAI models we support. Values are the bare model ids (what goes in .env).

    Being a ``str`` Enum, a member is interchangeable with its id string, so it can
    be used directly as a setting default or passed straight to :func:`build_agent`.
    """

    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4_1 = "gpt-4.1"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1_NANO = "gpt-4.1-nano"
    O3 = "o3"
    O3_MINI = "o3-mini"
    O4_MINI = "o4-mini"

    @property
    def model_id(self) -> str:
        """Provider-qualified id understood by pydantic-ai (e.g. ``openai:gpt-4o``)."""
        return f"openai:{self.value}"


# A model may be given as an enum member, a bare name, a qualified id, an already-built
# pydantic-ai model object (e.g. TestModel in tests), or None (use the configured default).
ModelLike = OpenAIModel | str | Any | None
# One model, or an ordered fallback chain (first is primary, rest are tried on failure).
ModelsLike = ModelLike | Sequence[ModelLike]


def model_list(models: ModelsLike) -> list[Any]:
    """Normalize a single model or a chain into a list (always at least one entry)."""
    if models is None or isinstance(models, (str, OpenAIModel)):
        return [models]
    if isinstance(models, Sequence):
        return list(models) or [None]
    return [models]  # a single pre-built model object


def resolve_model(model: OpenAIModel | str | None = None) -> str:
    """Normalize a model reference to a pydantic-ai ``provider:model`` id string."""
    if model is None:
        from ..config import settings  # lazy import to avoid a config <-> llm cycle

        model = settings.openai_model
    if isinstance(model, OpenAIModel):
        return model.model_id
    return model if ":" in model else f"openai:{model}"


def _model_arg(model: ModelLike) -> Any:
    """Pass through a pre-built model object; otherwise resolve to an id string."""
    if model is None or isinstance(model, (OpenAIModel, str)):
        return resolve_model(model)
    return model


def build_agent(
    output_type: type[OutputT],
    *,
    model: ModelLike = None,
    system_prompt: str | None = None,
    retries: int = 2,
    name: str | None = None,
) -> Agent[None, OutputT]:
    """Construct a structured-output agent.

    `output_type` is the Pydantic model the LLM must return; pydantic-ai validates
    (and auto-retries) against it. `model` is anything :func:`_model_arg` accepts.
    `name` labels the agent in traces. Instrumentation is global (observability/tracing.py).
    """
    agent: Agent[None, OutputT] = Agent(
        model=_model_arg(model),
        output_type=output_type,
        system_prompt=system_prompt or "",
        retries=retries,
        name=name,
    )
    return agent


async def run_structured(
    prompt: str,
    output_type: type[OutputT],
    *,
    models: ModelsLike = None,
    system_prompt: str | None = None,
    agent: Agent[None, OutputT] | None = None,
    retries_per_model: int = 1,
    name: str | None = None,
) -> OutputT:
    """Structured LLM call with model fallback.

    Tries each model in `models` in order; each gets `retries_per_model` extra attempts
    before falling through to the next. `agent` (if given) bypasses fallback — used in tests.
    """
    if agent is not None:
        return (await agent.run(prompt)).output
    return await _with_fallback(
        lambda model: build_agent(output_type, model=model, system_prompt=system_prompt, name=name),
        prompt,
        models,
        retries_per_model,
        name,
    )


def build_text_agent(
    *,
    model: ModelLike = None,
    system_prompt: str | None = None,
    retries: int = 2,
    name: str | None = None,
) -> Agent[None, str]:
    """Agent that returns free-form text (plain-string output)."""
    agent: Agent[None, str] = Agent(
        model=_model_arg(model),
        output_type=str,
        system_prompt=system_prompt or "",
        retries=retries,
        name=name,
    )
    return agent


async def run_text(
    prompt: str,
    *,
    models: ModelsLike = None,
    system_prompt: str | None = None,
    agent: Agent[None, str] | None = None,
    retries_per_model: int = 1,
    name: str | None = None,
) -> str:
    """Free-text LLM call with model fallback (see :func:`run_structured`)."""
    if agent is not None:
        return (await agent.run(prompt)).output
    return await _with_fallback(
        lambda model: build_text_agent(model=model, system_prompt=system_prompt, name=name),
        prompt,
        models,
        retries_per_model,
        name,
    )


async def _with_fallback(
    make_agent: Callable[[ModelLike], Agent[None, Any]],
    prompt: str,
    models: ModelsLike,
    retries_per_model: int,
    name: str | None,
) -> Any:
    """Run a prompt across the model fallback chain.

    Each model is retried up to `retries_per_model` extra times, but ONLY for transient errors;
    a non-recoverable failure (auth, bad request, output validation) skips straight to the next
    model. Every intermediate failure is logged so silent fallback can't hide a misconfiguration.
    """
    last_err: Exception | None = None
    for model in model_list(models):
        agent = make_agent(model)
        for attempt in range(retries_per_model + 1):
            try:
                return (await agent.run(prompt)).output
            except Exception as err:
                last_err = err
                retryable = _is_retryable(err)
                log.warning(
                    "llm.attempt_failed",
                    agent=name,
                    model=str(model),
                    attempt=attempt,
                    retryable=retryable,
                    error=f"{type(err).__name__}: {err}",
                )
                if not retryable:
                    break  # don't burn retries on this model; try the next one in the chain
    raise last_err if last_err else RuntimeError("no model produced a result")
