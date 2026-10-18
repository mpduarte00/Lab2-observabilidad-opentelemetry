
import json
import logging
import os
import random
import sys
import time

from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from database import get_connection, init_db


# ============================================================
# CONFIGURACIÓN
# ============================================================

OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://otel-collector:4317",
)

CHAOS_LATENCY_MS = max(
    0,
    int(os.getenv("CHAOS_LATENCY_MS", "0")),
)

CHAOS_ERRORS_ENABLED = (
    os.getenv("CHAOS_ERRORS_ENABLED", "false").lower() == "true"
)

# Probabilidad de error HTTP 500: 0.10 equivale al 10 %.
CHAOS_ERROR_RATE = float(os.getenv("CHAOS_ERROR_RATE", "0.10"))
CHAOS_ERROR_RATE = min(max(CHAOS_ERROR_RATE, 0.0), 1.0)

resource = Resource.create(
    {
        "service.name": "service-b",
        "deployment.environment": os.getenv(
            "DEPLOYMENT_ENVIRONMENT",
            "kubernetes",
        ),
    }
)


# ============================================================
# TRAZAS
# ============================================================

trace_provider = TracerProvider(resource=resource)

trace_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=True,
        )
    )
)

trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer(__name__)


# ============================================================
# MÉTRICAS
# ============================================================

metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(
        endpoint=OTEL_EXPORTER_OTLP_ENDPOINT,
        insecure=True,
    ),
    export_interval_millis=5000,
)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[metric_reader],
)

metrics.set_meter_provider(meter_provider)

meter = metrics.get_meter("service-b")

requests_total = meter.create_counter(
    "service_b_requests_total",
    description="Total de solicitudes HTTP procesadas por Service B",
)

errors_total = meter.create_counter(
    "service_b_errors_total",
    description="Total de respuestas HTTP de error de Service B",
)

request_duration = meter.create_histogram(
    "service_b_request_duration_ms",
    unit="ms",
    description="Duración de las solicitudes HTTP de Service B",
)


# ============================================================
# LOGS OPENTELEMETRY
# ============================================================

logger_provider = LoggerProvider(resource=resource)

logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(
            endpoint=OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=True,
        )
    )
)

otel_logging_handler = LoggingHandler(
    level=logging.INFO,
    logger_provider=logger_provider,
)


# ============================================================
# LOGGER JSON CON TRACE_ID Y SPAN_ID
# ============================================================

logger = logging.getLogger("service-b")
logger.setLevel(logging.INFO)
logger.handlers.clear()

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        span = trace.get_current_span()
        context = span.get_span_context()

        trace_id = (
            format(context.trace_id, "032x")
            if context.is_valid
            else None
        )

        span_id = (
            format(context.span_id, "016x")
            if context.is_valid
            else None
        )

        log_data = {
            "message": record.getMessage(),
            "service": "service-b",
            "trace_id": trace_id,
            "span_id": span_id,
        }

        return json.dumps(log_data, ensure_ascii=False)


console_handler.setFormatter(JsonFormatter())

logger.addHandler(console_handler)
logger.addHandler(otel_logging_handler)
logger.propagate = False


def log_json(message):
    logger.info(message)


# ============================================================
# BASE DE DATOS
# ============================================================

init_db()


# ============================================================
# APLICACIÓN FASTAPI
# ============================================================

app = FastAPI(title="Service B")

# Instrumentación automática de trazas HTTP y SQLite.
FastAPIInstrumentor.instrument_app(app)
SQLite3Instrumentor().instrument()


# ============================================================
# MÉTRICAS HTTP
# ============================================================

@app.middleware("http")
async def collect_http_metrics(request, call_next):
    start = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response

    except Exception:
        status_code = 500
        raise

    finally:
        duration_ms = (time.perf_counter() - start) * 1000

        attributes = {
            "http.request.method": request.method,
            "http.route": request.url.path,
            "http.response.status_code": status_code,
        }

        requests_total.add(1, attributes)

        if status_code >= 400:
            errors_total.add(1, attributes)

        request_duration.record(duration_ms, attributes)


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================

@app.get("/")
def home():
    if CHAOS_LATENCY_MS > 0:
        log_json(
            f"Inyectando latencia artificial de {CHAOS_LATENCY_MS} ms"
        )
        time.sleep(CHAOS_LATENCY_MS / 1000)

    log_json("Consulta al endpoint principal")

    return {
        "service": "service-b",
        "message": "Hola desde Service B",
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    log_json("Consulta al endpoint de salud")

    return {
        "service": "service-b",
        "status": "ok",
    }


# ============================================================
# PRUEBA DE BASE DE DATOS
# ============================================================

@app.get("/db-test")
def db_test():
    with tracer.start_as_current_span("database-operation"):
        log_json("Iniciando operación en base de datos")

        connection = get_connection()

        try:
            cursor = connection.cursor()

            cursor.execute(
                "INSERT INTO requests (message) VALUES (?)",
                ("Prueba de Service B",),
            )

            connection.commit()

            cursor.execute("SELECT * FROM requests")
            rows = cursor.fetchall()

            log_json("Operación de base de datos completada")

            return {
                "database": "sqlite",
                "records": rows,
            }

        finally:
            connection.close()


# ============================================================
# ENDPOINT CONTROLADO PARA CHAOS ENGINEERING
# ============================================================

@app.get("/chaos-error")
def chaos_error():
    if not CHAOS_ERRORS_ENABLED:
        raise HTTPException(
            status_code=404,
            detail="Prueba de caos deshabilitada",
        )

    if random.random() < CHAOS_ERROR_RATE:
        log_json("Prueba controlada: generando HTTP 500")

        raise HTTPException(
            status_code=500,
            detail="Error controlado para prueba de observabilidad",
        )

    log_json("Prueba de caos: solicitud sin error")

    return {
        "service": "service-b",
        "chaos_test": True,
        "error_injected": False,
        "message": "Solicitud procesada sin error",
    }
