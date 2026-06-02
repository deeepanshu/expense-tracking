from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.settings import Settings

logger = logging.getLogger("expense_tracker")
tracer = trace.get_tracer("expense_tracker")
meter = metrics.get_meter("expense_tracker")

receipts_received_counter = meter.create_counter(
    "expense_tracker.receipts.received",
    description="Receipt image attachments received for processing.",
)
parse_success_counter = meter.create_counter(
    "expense_tracker.receipts.parse_success",
    description="Receipt images parsed successfully.",
)
parse_failure_counter = meter.create_counter(
    "expense_tracker.receipts.parse_failure",
    description="Receipt image parse failures.",
)
approvals_counter = meter.create_counter(
    "expense_tracker.receipts.approved",
    description="Receipt versions approved by a Discord user.",
)
rejections_counter = meter.create_counter(
    "expense_tracker.receipts.rejected",
    description="Receipt versions rejected by a Discord user.",
)
image_size_histogram = meter.create_histogram(
    "expense_tracker.receipts.image_size_bytes",
    unit="By",
    description="Uploaded receipt image size in bytes.",
)
parse_duration_histogram = meter.create_histogram(
    "expense_tracker.receipts.parse_duration_seconds",
    unit="s",
    description="End-to-end AI receipt parse duration in seconds.",
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = trace.get_current_span().get_span_context().trace_id
        if trace_id:
            payload["trace_id"] = f"{trace_id:032x}"
        for key, value in vars(record).items():
            if key.startswith("expense_"):
                payload[key.removeprefix("expense_")] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_telemetry(settings: Settings) -> None:
    configure_logging()
    if not settings.otel_enabled:
        logger.info("OpenTelemetry disabled")
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(trace_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/metrics")
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))
    logger.info(
        "OpenTelemetry configured",
        extra={"expense_otlp_endpoint": settings.otel_exporter_otlp_endpoint},
    )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


@contextmanager
def record_duration(histogram: Any, attributes: dict[str, str] | None = None) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        histogram.record(time.perf_counter() - start, attributes or {})
