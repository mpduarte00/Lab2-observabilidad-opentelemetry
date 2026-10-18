import httpx
import json
import logging
import sys
import time

from fastapi import FastAPI

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource

# ============================================================
# TRAZAS
# ============================================================

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# ============================================================
# MÉTRICAS
# ============================================================

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# ============================================================
# LOGS OTEL
# ============================================================

from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs import LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

# ============================================================
# INSTRUMENTACIÓN
# ============================================================

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor


# ============================================================
# RECURSOS
# ============================================================

resource = Resource.create({
    "service.name": "service-a"
})


# ============================================================
# TRAZAS
# ============================================================

trace.set_tracer_provider(
    TracerProvider(resource=resource)
)

tracer = trace.get_tracer(__name__)

otlp_trace_exporter = OTLPSpanExporter(
    endpoint="http://127.0.0.1:4317",
    insecure=True
)

trace.get_tracer_provider().add_span_processor(
    SimpleSpanProcessor(otlp_trace_exporter)
)


# ============================================================
# MÉTRICAS
# ============================================================

otlp_metric_exporter = OTLPMetricExporter(
    endpoint="http://127.0.0.1:4317",
    insecure=True
)

metric_reader = PeriodicExportingMetricReader(
    otlp_metric_exporter,
    export_interval_millis=5000
)

metrics.set_meter_provider(
    MeterProvider(
        resource=resource,
        metric_readers=[metric_reader]
    )
)

meter = metrics.get_meter(__name__)


request_counter = meter.create_counter(
    "service_a_requests_total",
    description="Número total de solicitudes recibidas por Service A"
)

error_counter = meter.create_counter(
    "service_a_errors_total",
    description="Número total de errores en Service A"
)

request_duration = meter.create_histogram(
    "service_a_request_duration_ms",
    description="Duración de las solicitudes de Service A en milisegundos",
    unit="ms"
)


# ============================================================
# LOGS OPENTELEMETRY
# ============================================================

logger_provider = LoggerProvider(
    resource=resource
)

otlp_log_exporter = OTLPLogExporter(
    endpoint="http://127.0.0.1:4317",
    insecure=True
)

logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(otlp_log_exporter)
)

otel_logging_handler = LoggingHandler(
    level=logging.INFO,
    logger_provider=logger_provider
)


# ============================================================
# LOGS JSON EN CONSOLA
# ============================================================

class JsonFormatter(logging.Formatter):

    def format(self, record):

        span = trace.get_current_span()
        context = span.get_span_context()

        log_data = {
            "message": record.getMessage(),
            "service": "service-a",
            "trace_id": format(context.trace_id, "032x"),
            "span_id": format(context.span_id, "016x")
        }

        return json.dumps(log_data)


console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(JsonFormatter())


logger = logging.getLogger("service-a")
logger.setLevel(logging.INFO)
logger.handlers.clear()

# Log JSON por consola
logger.addHandler(console_handler)

# Log OTLP hacia el Collector
logger.addHandler(otel_logging_handler)

logger.propagate = False


def log_json(message):
    logger.info(message)


# ============================================================
# APLICACIÓN
# ============================================================

app = FastAPI(title="Service A")

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================

@app.get("/")
def home():

    start_time = time.perf_counter()

    try:

        request_counter.add(
            1,
            {
                "endpoint": "/",
                "method": "GET"
            }
        )

        log_json("Consulta al endpoint principal")

        return {
            "service": "service-a",
            "message": "Hola desde Service A"
        }

    except Exception:

        error_counter.add(
            1,
            {
                "endpoint": "/",
                "method": "GET"
            }
        )

        raise

    finally:

        duration = (time.perf_counter() - start_time) * 1000

        request_duration.record(
            duration,
            {
                "endpoint": "/",
                "method": "GET"
            }
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    start_time = time.perf_counter()

    try:

        request_counter.add(
            1,
            {
                "endpoint": "/health",
                "method": "GET"
            }
        )

        log_json("Consulta al endpoint de salud")

        return {
            "service": "service-a",
            "status": "ok"
        }

    except Exception:

        error_counter.add(
            1,
            {
                "endpoint": "/health",
                "method": "GET"
            }
        )

        raise

    finally:

        duration = (time.perf_counter() - start_time) * 1000

        request_duration.record(
            duration,
            {
                "endpoint": "/health",
                "method": "GET"
            }
        )


# ============================================================
# COMUNICACIÓN CON SERVICE B
# ============================================================

@app.get("/service-b")
def call_service_b():

    start_time = time.perf_counter()

    try:

        request_counter.add(
            1,
            {
                "endpoint": "/service-b",
                "method": "GET"
            }
        )

        with tracer.start_as_current_span("call-service-b"):

            log_json("Llamando a Service B")

            response = httpx.get(
                "http://127.0.0.1:8002/"
            )

            response.raise_for_status()

            log_json("Respuesta recibida de Service B")

            return {
                "service": "service-a",
                "response_from_service_b": response.json()
            }

    except Exception:

        error_counter.add(
            1,
            {
                "endpoint": "/service-b",
                "method": "GET"
            }
        )

        raise

    finally:

        duration = (time.perf_counter() - start_time) * 1000

        request_duration.record(
            duration,
            {
                "endpoint": "/service-b",
                "method": "GET"
            }
        )