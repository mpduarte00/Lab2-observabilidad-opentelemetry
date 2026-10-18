import json
import logging
import sys

from fastapi import FastAPI

from database import init_db, get_connection

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor


# ============================================================
# CONFIGURACIÓN DE OPENTELEMETRY
# ============================================================

resource = Resource.create({
    "service.name": "service-b"
})


# ============================================================
# TRAZAS
# ============================================================

trace.set_tracer_provider(
    TracerProvider(resource=resource)
)

tracer = trace.get_tracer(__name__)


# Enviar trazas al OTel Collector
otlp_trace_exporter = OTLPSpanExporter(
    endpoint="http://127.0.0.1:4317",
    insecure=True
)

trace.get_tracer_provider().add_span_processor(
    SimpleSpanProcessor(otlp_trace_exporter)
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
# LOGGER
# ============================================================

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO
)

logger = logging.getLogger("service-b")

logger.addHandler(otel_logging_handler)

logger.propagate = False


# ============================================================
# FUNCIÓN PARA GENERAR LOGS JSON
# ============================================================

def log_json(message):
    span = trace.get_current_span()
    context = span.get_span_context()

    log_data = {
        "message": message,
        "service": "service-b",
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x")
    }

    logger.info(json.dumps(log_data))


# ============================================================
# BASE DE DATOS
# ============================================================

init_db()


# ============================================================
# APLICACIÓN
# ============================================================

app = FastAPI(title="Service B")


# Instrumentación automática de FastAPI
FastAPIInstrumentor.instrument_app(app)


# Instrumentación automática de SQLite
SQLite3Instrumentor().instrument()


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================

@app.get("/")
def home():

    log_json("Consulta al endpoint principal")

    return {
        "service": "service-b",
        "message": "Hola desde Service B"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    log_json("Consulta al endpoint de salud")

    return {
        "service": "service-b",
        "status": "ok"
    }


# ============================================================
# PRUEBA DE BASE DE DATOS
# ============================================================

@app.get("/db-test")
def db_test():

    with tracer.start_as_current_span("database-operation"):

        log_json("Iniciando operación en base de datos")

        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "INSERT INTO requests (message) VALUES (?)",
            ("Prueba de Service B",)
        )

        connection.commit()

        cursor.execute("SELECT * FROM requests")
        rows = cursor.fetchall()

        connection.close()

        log_json("Operación de base de datos completada")

        return {
            "database": "sqlite",
            "records": rows
        }