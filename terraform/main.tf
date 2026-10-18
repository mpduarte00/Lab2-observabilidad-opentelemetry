terraform {
  required_version = ">= 1.5.0"

  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

provider "local" {}

resource "local_file" "observability_architecture" {
  filename = "${path.module}/observability-architecture.txt"

  content = <<-EOT
    ARQUITECTURA DE OBSERVABILIDAD - LABORATORIO

    Servicios:
    - Service A: http://127.0.0.1:8000
    - Service B: http://127.0.0.1:8002

    Observabilidad:
    - OpenTelemetry SDK
    - OpenTelemetry Collector
    - Jaeger
    - Prometheus
    - Grafana
    - Loki

    Protocolos:
    - OTLP gRPC: 4317
    - OTLP HTTP: 4318

    Flujo:
    Service A -> Service B
    Service A/B -> OpenTelemetry Collector

    Collector:
    - Traces -> Jaeger
    - Metrics -> Prometheus
    - Logs -> Loki

    Correlación:
    - trace_id
    - span_id
    - W3C Trace Context
  EOT
}