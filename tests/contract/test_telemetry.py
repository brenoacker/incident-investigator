from __future__ import annotations

import asyncio
import uuid

import httpx
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from incident_investigation_harness.app import app
from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.telemetry import (
    Telemetry,
    context_attributes,
    configure_telemetry,
    record_model_execution,
    record_report_collection,
    span,
)


def test_span_contains_run_correlation_but_no_sensitive_content() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry_reader = InMemoryMetricReader()
    application_telemetry = configure_telemetry(
        service_name="test-service",
        tracer_provider=tracer_provider,
        meter_provider=MeterProvider(metric_readers=[telemetry_reader]),
    )
    application_telemetry.tickets_created.add(1)
    context = InvestigationContext(
        incident_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        investigation_run_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    )

    with span(
        "test-operation",
        context=context,
        component="test",
        operation="query",
        attributes={"result": "success"},
    ):
        pass

    exported = exporter.get_finished_spans()
    assert len(exported) == 1
    attributes = dict(exported[0].attributes)
    assert attributes["incident_id"] == str(context.incident_id)
    assert attributes["investigation_run_id"] == str(context.investigation_run_id)
    assert "secret" not in attributes
    assert telemetry_reader.get_metrics_data().resource_metrics


def test_span_records_failure_without_leaking_exception_details_to_attributes() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    configure_telemetry(
        service_name="failure-test",
        tracer_provider=provider,
        meter_provider=MeterProvider(metric_readers=[InMemoryMetricReader()]),
    )

    try:
        with span("failed-operation", component="test", operation="fail"):
            raise RuntimeError("token=must-not-be-an-attribute")
    except RuntimeError:
        pass

    finished = exporter.get_finished_spans()[0]
    assert finished.status.status_code.name == "ERROR"
    assert all("token=must-not" not in str(value) for value in finished.attributes.values())
    assert all(
        "token=must-not" not in str(event.attributes)
        for event in finished.events
    )


def test_metrics_endpoint_is_available_without_observability_backends() -> None:
    async def request_metrics() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/metrics/")

    response = asyncio.run(request_metrics())
    assert response.status_code == 200
    assert "# HELP" in response.text


def test_context_attributes_are_bounded_and_explicit() -> None:
    context = InvestigationContext(
        incident_id=uuid.uuid4(), investigation_run_id=uuid.uuid4()
    )
    attributes = context_attributes(
        context,
        component="operations-mcp",
        operation="query",
        scenario="retry-storm",
    )
    assert set(attributes) == {
        "component", "operation", "incident_id", "investigation_run_id", "scenario"
    }


def test_ai_telemetry_marks_optional_usage_as_unavailable_and_keeps_correlation_on_span() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    application_telemetry = configure_telemetry(
        service_name="ai-test",
        tracer_provider=provider,
        meter_provider=MeterProvider(metric_readers=[InMemoryMetricReader()]),
    )
    context = InvestigationContext(incident_id=uuid.uuid4(), investigation_run_id=uuid.uuid4())

    with span(
        "investigation-model-execution",
        context=context,
        component="codex-investigator",
        operation="model.execute",
        attributes={"model_version": "test-model", "prompt_version": "prompt-v1"},
    ):
        record_model_execution(
            context=context,
            scenario="retry-storm",
            model_version="test-model",
            prompt_version="prompt-v1",
            duration_seconds=0.25,
            input_tokens=None,
            output_tokens=None,
            estimated_cost=None,
            outcome="success",
        )
        record_report_collection(
            context=context,
            scenario="retry-storm",
            size_bytes=512,
            claim_count=2,
        )

    finished = exporter.get_finished_spans()[0]
    assert dict(finished.attributes)["incident_id"] == str(context.incident_id)
    assert dict(finished.attributes)["prompt_version"] == "prompt-v1"
    assert "estimated_cost" not in finished.attributes
    assert "evidence" not in str(finished.attributes).casefold()
    assert application_telemetry.model_usage is not None
