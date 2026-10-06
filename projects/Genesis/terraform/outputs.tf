output "cloud_run_url" {
  description = "Genesis backend URL"
  value       = google_cloud_run_v2_service.genesis.uri
}

output "frontend_url" {
  description = "Genesis frontend URL"
  value       = google_cloud_run_v2_service.genesis_frontend.uri
}

output "artifact_registry" {
  description = "Docker registry URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.genesis.repository_id}"
}

output "cloud_sql_instance" {
  description = "Cloud SQL instance connection name"
  value       = google_sql_database_instance.genesis.connection_name
}

output "cloud_sql_private_ip" {
  description = "Cloud SQL private IP"
  value       = google_sql_database_instance.genesis.private_ip_address
  sensitive   = true
}

output "db_password" {
  description = "Database password for genesis_app user"
  value       = random_password.db_password.result
  sensitive   = true
}

output "database_url" {
  description = "Full Postgres connection string (via private IP)"
  value       = "postgresql://${var.db_user}:${random_password.db_password.result}@${google_sql_database_instance.genesis.private_ip_address}:5432/${var.db_name}"
  sensitive   = true
}

output "cloud_run_service_account" {
  description = "Cloud Run service account email"
  value       = google_service_account.cloud_run.email
}

output "github_actions_service_account" {
  description = "GitHub Actions service account email"
  value       = google_service_account.github_actions.email
}
