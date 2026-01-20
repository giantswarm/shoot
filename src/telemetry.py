"""
OpenTelemetry instrumentation for the Shoot agent system.

This module configures distributed tracing for:
- Coordinator agent operations
- Collector subagent delegations
- MCP tool calls
- API request handling

Environment variables:
- OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint URL (e.g., http://localhost:4317)
- OTEL_SERVICE_NAME: Service name (default: "shoot")
- OTEL_TRACES_EXPORTER: Exporter type (default: "otlp")
"""

import os
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.trace import Status, StatusCode, Span

# Conditionally import OTLP exporter (may not be available in all environments)
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    OTLP_AVAILABLE = True
except ImportError:
    OTLP_AVAILABLE = False


def init_telemetry() -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing.

    Returns a tracer instance configured based on environment variables.
    If OTEL_EXPORTER_OTLP_ENDPOINT is set, uses OTLP exporter.
    Otherwise, uses console exporter for local development.
    """
    service_name = os.environ.get("OTEL_SERVICE_NAME", "shoot")

    # Create resource with service name
    resource = Resource.create({SERVICE_NAME: service_name})

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Configure exporter based on environment
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if otlp_endpoint and OTLP_AVAILABLE:
        # Production: OTLP exporter
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    elif os.environ.get("OTEL_TRACES_EXPORTER") == "console":
        # Development: Console exporter
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    # else: No exporter (tracing disabled but API still works)

    # Set global tracer provider
    trace.set_tracer_provider(provider)

    return trace.get_tracer(__name__)


# Global tracer instance
_tracer: trace.Tracer | None = None


def get_tracer() -> trace.Tracer:
    """Get or create the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = init_telemetry()
    return _tracer


@contextmanager
def trace_operation(
    name: str, attributes: dict[str, Any] | None = None
) -> Generator[Span, None, None]:
    """
    Context manager for tracing an operation.

    Usage:
        with trace_operation("coordinator.investigate", {"query": query}) as span:
            # ... do work ...
            span.set_attribute("result.turns", 5)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, _sanitize_attribute(value))
        try:
            yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def _sanitize_attribute(value: Any) -> Any:
    """Sanitize attribute values for OpenTelemetry (must be primitive types)."""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_sanitize_attribute(v) for v in value]
    return str(value)


# Convenience functions for common span operations
def add_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add an event to the current span."""
    span = trace.get_current_span()
    if span:
        span.add_event(name, attributes=attributes or {})


def set_span_attribute(key: str, value: Any) -> None:
    """Set an attribute on the current span."""
    span = trace.get_current_span()
    if span:
        span.set_attribute(key, _sanitize_attribute(value))


def set_span_error(error: Exception) -> None:
    """Mark the current span as errored."""
    span = trace.get_current_span()
    if span:
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.record_exception(error)
