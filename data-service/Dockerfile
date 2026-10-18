FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN mkdir -p /app/data

ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENV DB_PATH=/app/data/data-service.db

EXPOSE 8003

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
