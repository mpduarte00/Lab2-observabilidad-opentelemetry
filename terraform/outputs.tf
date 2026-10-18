output "project_name" {
  description = "Nombre del proyecto"
  value       = var.project_name
}

output "environment" {
  description = "Ambiente de ejecución"
  value       = var.environment
}

output "service_a_url" {
  description = "URL local de Service A"
  value       = "http://127.0.0.1:${var.service_a_port}"
}

output "service_b_url" {
  description = "URL local de Service B"
  value       = "http://127.0.0.1:${var.service_b_port}"
}

output "otel_grpc_endpoint" {
  description = "Endpoint OTLP gRPC"
  value       = "127.0.0.1:${var.otel_grpc_port}"
}

output "otel_http_endpoint" {
  description = "Endpoint OTLP HTTP"
  value       = "127.0.0.1:${var.otel_http_port}"
}