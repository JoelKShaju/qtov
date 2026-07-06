"""LLM/agent tracing via Pydantic AI's OpenTelemetry instrumentation.

Pluggable and env-gated: send to Logfire (LOGFIRE_TOKEN), to any OTLP collector
such as Langfuse/Datadog (OTEL_EXPORTER_OTLP_ENDPOINT), or no-op if neither is set.
The app always runs; observability is purely additive.
"""

from __future__ import annotations

from ..config import settings
from .logging import get_logger

log = get_logger(__name__)


def configure_tracing() -> None:
    if settings.logfire_token:
        try:
            import logfire

            logfire.configure(
                token=settings.logfire_token,
                service_name=settings.service_name,
                send_to_logfire=True,
                console=False,
            )
            logfire.instrument_pydantic_ai()
            log.info("tracing.enabled", backend="logfire")
            return
        except Exception as exc:  # pragma: no cover - optional dependency
            log.warning("tracing.logfire_failed", error=str(exc))

    if settings.otel_exporter_otlp_endpoint:
        try:
            import logfire

            # Exports via OTLP to OTEL_EXPORTER_OTLP_ENDPOINT (set in the env).
            logfire.configure(
                service_name=settings.service_name,
                send_to_logfire=False,
                console=False,
            )
            logfire.instrument_pydantic_ai()
            log.info(
                "tracing.enabled",
                backend="otlp",
                endpoint=settings.otel_exporter_otlp_endpoint,
            )
            return
        except Exception as exc:  # pragma: no cover - optional dependency
            log.warning("tracing.otlp_failed", error=str(exc))

    log.info(
        "tracing.disabled",
        note="set LOGFIRE_TOKEN or OTEL_EXPORTER_OTLP_ENDPOINT to export LLM traces",
    )
