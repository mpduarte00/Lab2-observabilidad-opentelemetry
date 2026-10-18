variable "project_name" {
  description = "Nombre del proyecto de observabilidad"
  type        = string
  default     = "lab1-observabilidad-opentelemetry"
}

variable "environment" {
  description = "Ambiente de ejecución"
  type        = string
  default     = "local"
}

variable "service_a_port" {
  description = "Puerto de Service A"
  type        = number
  default     = 8000
}

variable "service_b_port" {
  description = "Puerto de Service B"
  type        = number
  default     = 8002
}

variable "otel_grpc_port" {
  description = "Puerto OTLP gRPC del Collector"
  type        = number
  default     = 4317
}

variable "otel_http_port" {
  description = "Puerto OTLP HTTP del Collector"
  type        = number
  default     = 4318
}