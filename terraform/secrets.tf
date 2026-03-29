resource "google_secret_manager_secret" "database_url" {
  secret_id = "genesis-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis["secretmanager.googleapis.com"]]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql://${google_sql_user.genesis_app.name}:${random_password.db_password.result}@${google_sql_database_instance.genesis.private_ip_address}:5432/${google_sql_database.genesis.name}"
}

resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "genesis-openai-api-key"

  replication {
    auto {}
  }

  lifecycle {
    ignore_changes = [labels]
  }
}

resource "google_secret_manager_secret_version" "openai_api_key" {
  secret      = google_secret_manager_secret.openai_api_key.id
  secret_data = var.openai_api_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "genesis-anthropic-api-key"

  replication {
    auto {}
  }

  lifecycle {
    ignore_changes = [labels]
  }
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}
