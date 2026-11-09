"""OpenTelemetry setup: traces, metrics and logs to Dash0 over OTLP/HTTP.

Enabled only when OTEL_EXPORTER_OTLP_ENDPOINT is set, so tests and local runs
without credentials are unaffected. The Elasticsearch client emits its own
spans once a tracer provider exists, so every search/rerank/geo query shows up
as a child span of the HTTP request.

Env:
  OTEL_EXPORTER_OTLP_ENDPOINT   e.g. https://ingress.<region>.aws.dash0.com
  DASH0_AUTH_TOKEN              Dash0 auth token (sent as a Bearer header)
  DASH0_DATASET                 optional Dash0 dataset name
  OTEL_SERVICE_NAME             defaults to "hallpass"
"""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace

log = logging.getLogger("hallpass")

_meter = metrics.get_meter("hallpass")
searches = _meter.create_counter(
    "hallpass.searches", description="Search-type requests by kind and outcome"
)
results_returned = _meter.create_histogram(
    "hallpass.results", description="Posters returned per request", unit="{poster}"
)
route_length = _meter.create_histogram(
    "hallpass.route.length", description="Planned walking route length", unit="m"
)
tracer = trace.get_tracer("hallpass")


def _headers() -> dict[str, str]:
    h = {}
    if token := os.getenv("DASH0_AUTH_TOKEN"):
        h["Authorization"] = f"Bearer {token}"
    if dataset := os.getenv("DASH0_DATASET"):
        h["Dash0-Dataset"] = dataset
    return h


def setup(app) -> bool:
    """Wire up OTel exporters and auto-instrumentation. Returns True if enabled."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
    if not endpoint:
        return False

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "hallpass"),
        "service.version": os.getenv("APP_VERSION", "dev"),
        "deployment.environment.name": os.getenv("DEPLOY_ENV", "local"),
    })
    headers = _headers()

    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers)))
    trace.set_tracer_provider(tp)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", headers=headers),
        export_interval_millis=15_000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    lp = LoggerProvider(resource=resource)
    lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers)))
    set_logger_provider(lp)
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=lp))
    logging.getLogger().setLevel(logging.INFO)

    # Health probes would drown out real traffic.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")
    HTTPXClientInstrumentor().instrument()
    log.info("telemetry enabled", extra={"otlp.endpoint": endpoint})
    return True
