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
        self.model_executions = meter.create_counter(
            "investigation_model_executions", unit="{execution}"
        )
        self.model_duration = meter.create_histogram(
            "investigation_model_duration", unit="s"
        )
        self.model_input_tokens = meter.create_counter(
            "investigation_model_input_tokens", unit="{token}"
        )
        self.model_output_tokens = meter.create_counter(
            "investigation_model_output_tokens", unit="{token}"
        )
        self.model_cost = meter.create_counter(
            "investigation_model_cost", unit="{currency}"
        )
        self.model_usage = meter.create_counter(
            "investigation_model_usage", unit="{observation}"
        )
        self.model_retries = meter.create_counter(
            "investigation_model_retries", unit="{retry}"
        )
        self.reports_collected = meter.create_counter(
            "investigation_reports_collected", unit="{report}"
        )
        self.report_size = meter.create_histogram(
            "investigation_report_size", unit="By"
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
        self.quality_gate_verdicts = meter.create_counter(
            "quality_gate_verdicts", unit="{verdict}"
        )
        self.quality_gate_citation_failures = meter.create_counter(
            "quality_gate_citation_failures", unit="{failure}"
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
    with tracer.start_as_current_span(
        name,
        attributes=safe_attributes,
        record_exception=False,
        set_status_on_exception=False,
    ) as current:
        try:
            yield current
        except Exception as error:
            # Exception messages can contain prompts, credentials or retrieved
            # evidence. The exception type is enough for operational tracing.
            current.set_status(Status(StatusCode.ERROR, type(error).__name__))
            raise


def mark_success(current: Span) -> None:
    current.set_status(Status(StatusCode.OK))


def record_model_execution(
    *,
    context: object,
    scenario: str,
    model_version: str,
    prompt_version: str,
    duration_seconds: float,
    input_tokens: int | None,
    output_tokens: int | None,
    estimated_cost: float | None,
    outcome: str,
    failure_category: str | None = None,
    retries: int = 0,
) -> None:
    """Record provider-neutral model telemetry without recording model content."""
    labels = {
        "scenario": scenario,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "outcome": outcome,
    }
    if failure_category is not None:
        labels["failure_category"] = failure_category
    telemetry.model_executions.add(1, labels)
    telemetry.model_duration.record(duration_seconds, labels)
    for field, value in (
        ("input_tokens", input_tokens),
        ("output_tokens", output_tokens),
        ("estimated_cost", estimated_cost),
    ):
        telemetry.model_usage.add(
            1,
            {
                **labels,
                "field": field,
                "availability": "available" if value is not None else "unavailable",
            },
        )
    if input_tokens is not None:
        telemetry.model_input_tokens.add(input_tokens, labels)
    if output_tokens is not None:
        telemetry.model_output_tokens.add(output_tokens, labels)
    if estimated_cost is not None:
        telemetry.model_cost.add(estimated_cost, labels)
    if retries:
        telemetry.model_retries.add(retries, labels)


def record_report_collection(
    *, context: object, scenario: str, size_bytes: int
) -> None:
    """Record report shape and size; never record report text or citations."""
    labels = {"scenario": scenario}
    telemetry.reports_collected.add(1, labels)
    telemetry.report_size.record(size_bytes, labels)


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
