
import json
import logging
import os
import sys
import time
import sqlite3
from pathlib import Path

import psycopg
import pymysql
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode


# ---------------------------------------------------------
# Configuración
# ---------------------------------------------------------

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://otel-collector:4317",
)

DB_PATH = Path(os.getenv("DB_PATH", "/app/data/data-service.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "host.docker.internal")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "observability_cloudsql")
POSTGRES_USER = os.getenv("POSTGRES_USER", "mduart1")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

MYSQL_HOST = os.getenv("MYSQL_HOST", "host.docker.internal")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_DB = os.getenv("MYSQL_DB", "observability_rds")
MYSQL_USER = os.getenv("MYSQL_USER", "observability")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")

resource = Resource.create({
    "service.name": "data-service",
    "deployment.environment": os.getenv(
        "DEPLOYMENT_ENVIRONMENT", "kubernetes"
    ),
})


# ---------------------------------------------------------
# OpenTelemetry: trazas
# ---------------------------------------------------------

trace_provider = TracerProvider(resource=resource)
trace_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
    )
)
trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer("data-service")


# ---------------------------------------------------------
# OpenTelemetry: métricas
# ---------------------------------------------------------

metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=OTEL_ENDPOINT, insecure=True),
    export_interval_millis=5000,
)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[metric_reader],
)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("data-service")

requests_total = meter.create_counter(
    "data_service_requests_total",
    description="Total de solicitudes procesadas por data-service",
)

db_operations_total = meter.create_counter(
    "data_service_db_operations_total",
    description="Total de operaciones de base de datos",
)

request_duration = meter.create_histogram(
    "data_service_request_duration_ms",
    unit="ms",
    description="Duración de las solicitudes de data-service",
)

db_operation_duration = meter.create_histogram(
    "data_service_db_operation_duration_ms",
    unit="ms",
    description="Duración de operaciones en bases de datos",
)


# ---------------------------------------------------------
# OpenTelemetry: logs
# ---------------------------------------------------------

logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=OTEL_ENDPOINT, insecure=True)
    )
)

otel_handler = LoggingHandler(
    level=logging.INFO,
    logger_provider=logger_provider,
)

logger = logging.getLogger("data-service")
logger.setLevel(logging.INFO)
logger.handlers.clear()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        context = trace.get_current_span().get_span_context()

        trace_id = (
            format(context.trace_id, "032x")
            if context.is_valid else None
        )
        span_id = (
            format(context.span_id, "016x")
            if context.is_valid else None
        )

        return json.dumps({
            "message": record.getMessage(),
            "service": "data-service",
            "trace_id": trace_id,
            "span_id": span_id,
            "level": record.levelname,
        }, ensure_ascii=False)


console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(JsonFormatter())
logger.addHandler(console_handler)
logger.addHandler(otel_handler)
logger.propagate = False


# ---------------------------------------------------------
# Instrumentación SQLite existente
# ---------------------------------------------------------

SQLite3Instrumentor().instrument()


def init_db():
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


init_db()


# ---------------------------------------------------------
# Aplicación FastAPI
# ---------------------------------------------------------

app = FastAPI(title="Data Service", version="1.1.0")
FastAPIInstrumentor.instrument_app(app)


@app.middleware("http")
async def collect_http_metrics(request, call_next):
    start = time.perf_counter()
    status = "500"

    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000

        attributes = {
            "http.request.method": request.method,
            "http.route": request.url.path,
            "http.response.status_code": status,
        }

        requests_total.add(1, attributes)
        request_duration.record(elapsed_ms, attributes)


# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "data-service",
    }


# ---------------------------------------------------------
# SQLite: endpoints existentes
# ---------------------------------------------------------

@app.post("/db-test")
def db_test(message: str = "observability-test"):
    start = time.perf_counter()

    try:
        with tracer.start_as_current_span(
            "data-service.database-operation"
        ) as span:
            span.set_attribute("db.system", "sqlite")
            span.set_attribute("db.operation.name", "INSERT")

            with sqlite3.connect(DB_PATH) as connection:
                cursor = connection.execute(
                    "INSERT INTO observations (message) VALUES (?)",
                    (message,),
                )
                observation_id = cursor.lastrowid

                count = connection.execute(
                    "SELECT COUNT(*) FROM observations"
                ).fetchone()[0]

            db_operations_total.add(
                2, {"db.system": "sqlite"}
            )

        logger.info(
            f"SQLite operation completed: id={observation_id}, "
            f"count={count}"
        )

        return {
            "service": "data-service",
            "database": "sqlite",
            "inserted_id": observation_id,
            "total_observations": count,
        }

    except Exception as exc:
        logger.exception("SQLite operation failed")
        raise HTTPException(
            status_code=500,
            detail="SQLite database operation failed",
        ) from exc

    finally:
        db_operation_duration.record(
            (time.perf_counter() - start) * 1000,
            {"db.system": "sqlite"},
        )


@app.get("/observations")
def observations():
    try:
        with sqlite3.connect(DB_PATH) as connection:
            rows = connection.execute(
                "SELECT id, message, created_at "
                "FROM observations ORDER BY id DESC LIMIT 20"
            ).fetchall()

        return {
            "service": "data-service",
            "database": "sqlite",
            "observations": [
                {
                    "id": row[0],
                    "message": row[1],
                    "created_at": row[2],
                }
                for row in rows
            ],
        }

    except Exception as exc:
        logger.exception("SQLite observations query failed")
        raise HTTPException(
            status_code=500,
            detail="SQLite query failed",
        ) from exc


# ---------------------------------------------------------
# PostgreSQL: simulación local de Cloud SQL
# ---------------------------------------------------------

@app.get("/postgres-test")
def postgres_test():
    start = time.perf_counter()
    db_attributes = {"db.system": "postgresql"}

    try:
        with tracer.start_as_current_span(
            "data-service.postgresql-operation"
        ) as span:
            span.set_attribute("db.system", "postgresql")
            span.set_attribute("db.namespace", POSTGRES_DB)
            span.set_attribute("db.operation.name", "SELECT")

            with psycopg.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                dbname=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                connect_timeout=5,
            ) as connection:
                row = connection.execute(
                    "SELECT current_database(), version()"
                ).fetchone()

            db_operations_total.add(1, db_attributes)

        logger.info(
            f"PostgreSQL connection successful: database={row[0]}"
        )

        return {
            "service": "data-service",
            "database": "postgresql",
            "database_name": row[0],
            "version": row[1],
            "status": "connected",
        }

    except Exception as exc:
        logger.exception("PostgreSQL operation failed")
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL connection failed; check connectivity and configuration",
        ) from exc

    finally:
        db_operation_duration.record(
            (time.perf_counter() - start) * 1000,
            db_attributes,
        )


# ---------------------------------------------------------
# MySQL: simulación local de Amazon RDS
# ---------------------------------------------------------

@app.get("/mysql-test")
def mysql_test():
    start = time.perf_counter()
    db_attributes = {"db.system": "mysql"}

    try:
        with tracer.start_as_current_span(
            "data-service.mysql-operation"
        ) as span:
            span.set_attribute("db.system", "mysql")
            span.set_attribute("db.namespace", MYSQL_DB)
            span.set_attribute("db.operation.name", "SELECT")

            connection = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                database=MYSQL_DB,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                connect_timeout=5,
                cursorclass=pymysql.cursors.DictCursor,
            )

            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT DATABASE() AS database_name, "
                        "VERSION() AS version"
                    )
                    row = cursor.fetchone()
            finally:
                connection.close()

            db_operations_total.add(1, db_attributes)

        logger.info(
            f"MySQL connection successful: database={row['database_name']}"
        )

        return {
            "service": "data-service",
            "database": "mysql",
            "database_name": row["database_name"],
            "version": row["version"],
            "status": "connected",
        }

    except Exception as exc:
        logger.exception("MySQL operation failed")
        raise HTTPException(
            status_code=503,
            detail="MySQL connection failed; check connectivity and configuration",
        ) from exc

    finally:
        db_operation_duration.record(
            (time.perf_counter() - start) * 1000,
            db_attributes,
        )
