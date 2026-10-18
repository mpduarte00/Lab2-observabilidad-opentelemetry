import logging
import sys

from fastapi import FastAPI

from database import init_db, get_connection


# ============================================================
# CONFIGURACIÓN DE LOGS
# ============================================================

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO
)

logger = logging.getLogger("service-b")


# ============================================================
# BASE DE DATOS
# ============================================================

init_db()


# ============================================================
# APLICACIÓN
# ============================================================

app = FastAPI(title="Service B")


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================

@app.get("/")
def home():
    logger.info("Consulta al endpoint principal")

    return {
        "service": "service-b",
        "message": "Hola desde Service B"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    logger.info("Consulta al endpoint de salud")

    return {
        "service": "service-b",
        "status": "ok"
    }


# ============================================================
# PRUEBA DE BASE DE DATOS
# ============================================================

@app.get("/db-test")
def db_test():
    logger.info("Iniciando operación en base de datos")

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

    logger.info("Operación de base de datos completada")

    return {
        "database": "sqlite",
        "records": rows
    }