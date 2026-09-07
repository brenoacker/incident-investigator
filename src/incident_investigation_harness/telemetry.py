"""Safe, local-first OpenTelemetry configuration and instrumentation helpers."""

from __future__ import annotations

import os
from functools import wraps
from inspect import signature
from time import perf_counter
from contextlib import contextmanager
from typing import Callable, Iterator, Mapping, ParamSpec, TypeVar

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

SERVICE_NAME = "incident-investigation-harness"
P = ParamSpec("P")
R = TypeVar("R")


class Telemetry:
    """Application metrics with only bounded-cardinality labels."""

    def __init__(self, meter: metrics.Meter) -> None:
        self._meter = meter
        self.runs_started = meter.create_counter(
            "investigation_runs_started", unit="{run}"
        )
        self.runs_completed = meter.create_counter(
            "investigation_runs_completed", unit="{run}"
        )
        self.runs_failed = meter.create_counter("investigation_runs_failed", unit="{run}")
        self.run_duration = meter.create_histogram(
            "investigation_run_duration", unit="s"
        )
        self.provider_queries = meter.create_counter(
            "evidence_provider_queries", unit="{query}"
        )
        self.provider_failures = meter.create_counter(
            "evidence_provider_query_failures", unit="{query}"
        )
        self.provider_duration = meter.create_histogram(
            "evidence_provider_query_duration", unit="s"
        )
        self.quality_gate_calls = meter.create_counter("quality_gate_calls", unit="{call}")
        self.quality_gate_duration = meter.create_histogram(
            "quality_gate_duration", unit="s"
        )
        self.tickets_created = meter.create_counter("tickets_created", unit="{ticket}")
        self.notifications = meter.create_counter("notifications_total", unit="{notification}")
        self.notification_attempts = meter.create_counter(
            "notification_attempts", unit="{attempt}"
        )
        self.notification_retries = meter.create_counter(
            "notification_retries", unit="{retry}"
        )
        self.notification_backlog = meter.create_up_down_counter(
            "notification_backlog", unit="{message}"
        )
        self.notification_duration = meter.create_histogram(
            "notification_delivery_duration", unit="s"
        )


def _resource(service_name: str) -> Resource:
    return Resource.create({"service.name": service_name})


def configure_telemetry(
    *,
    service_name: str = SERVICE_NAME,
    otlp_endpoint: str | None = None,
    tracer_provider: TracerProvider | None = None,
    meter_provider: MeterProvider | None = None,
) -> Telemetry:
    """Configure providers without making telemetry a runtime dependency.

    Exporters are enabled only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or the
    explicit endpoint) is present. Export failures are handled by the SDK's
    asynchronous processors and never propagate to business code.
    """
    global tracer
    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    resource = _resource(service_name)
    if tracer_provider is None:
        tracer_provider = TracerProvider(resource=resource)
        if endpoint:
            tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
            )
    if meter_provider is None:
        readers: list[MetricReader] = []
        if os.getenv("OTEL_PROMETHEUS_ENABLED", "1") == "1":
            readers.append(PrometheusMetricReader())
        if endpoint:
            reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint, insecure=True)
            )
            readers.append(reader)
        meter_provider = MeterProvider(resource=resource, metric_readers=readers)
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)
    tracer = tracer_provider.get_tracer(service_name)
    return Telemetry(meter_provider.get_meter(service_name))


telemetry = configure_telemetry(service_name=os.getenv("OTEL_SERVICE_NAME", SERVICE_NAME))
tracer = trace.get_tracer(SERVICE_NAME)


def context_attributes(
    context: object | None = None,
    *,
    component: str,
    operation: str,
    scenario: str | None = None,
) -> dict[str, str]:
    """Return safe correlation attributes; never include evidence content."""
    attributes = {"component": component, "operation": operation}
    if context is not None:
        for name in ("incident_id", "investigation_run_id"):
            value = getattr(context, name, None)
            if value is not None:
                attributes[name] = str(value)
    if scenario is not None:
        attributes["scenario"] = scenario
    return attributes


@contextmanager
def span(
    name: str,
    *,
    context: object | None = None,
    component: str,
    operation: str,
    scenario: str | None = None,
    attributes: Mapping[str, str] | None = None,
) -> Iterator[Span]:
    """Create a correlated span and convert exceptions into error status."""
    safe_attributes = context_attributes(
        context, component=component, operation=operation, scenario=scenario
    )
    if attributes:
        safe_attributes.update(attributes)
    with tracer.start_as_current_span(name, attributes=safe_attributes) as current:
        try:
            yield current
        except Exception as error:
            current.record_exception(error)
            current.set_status(Status(StatusCode.ERROR, type(error).__name__))
            raise


def mark_success(current: Span) -> None:
    current.set_status(Status(StatusCode.OK))


def instrument_evidence_query(provider: str, operation: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a public MCP tool without adding evidence content to telemetry."""
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            import uuid

            try:
                bound = signature(function).bind_partial(*args, **kwargs).arguments
                context = type("EvidenceContext", (), {
                    "incident_id": uuid.UUID(str(bound.get("incident_id", ""))),
                    "investigation_run_id": uuid.UUID(str(bound.get("investigation_run_id", ""))),
                })()
            except (ValueError, IndexError, TypeError):
                context = None
            labels = {"provider": provider, "operation": operation}
            with span(
                f"{provider}.{operation}",
                context=context,
                component=provider,
                operation=operation,
            ):
                started = perf_counter()
                telemetry.provider_queries.add(1, labels)
                try:
                    result = function(*args, **kwargs)
                except Exception:
                    telemetry.provider_failures.add(1, labels)
                    raise
                finally:
                    telemetry.provider_duration.record(
                        perf_counter() - started, labels
                    )
                return result
        return wrapped
    return decorate
