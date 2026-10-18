import httpx
import logging
import sys

from fastapi import FastAPI


# ============================================================
# CONFIGURACIÓN DE LOGS
# ============================================================

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO
)

logger = logging.getLogger("service-a")


# ============================================================
# APLICACIÓN
# ============================================================

app = FastAPI(title="Service A")


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================

@app.get("/")
def home():
    logger.info("Consulta al endpoint principal")

    return {
        "service": "service-a",
        "message": "Hola desde Service A"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    logger.info("Consulta al endpoint de salud")

    return {
        "service": "service-a",
        "status": "ok"
    }


# ============================================================
# COMUNICACIÓN CON SERVICE B
# ============================================================

@app.get("/service-b")
def call_service_b():

    logger.info("Llamando a Service B")

    response = httpx.get(
        "http://127.0.0.1:8002/"
    )

    response.raise_for_status()

    logger.info("Respuesta recibida de Service B")

    return {
        "service": "service-a",
        "response_from_service_b": response.json()
    }