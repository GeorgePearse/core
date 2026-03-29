resource "google_sql_database_instance" "genesis" {
  name             = "genesis-postgres-${var.environment}"
  database_version = "POSTGRES_15"
  region           = var.region

  depends_on = [
    google_service_networking_connection.private_vpc,
    google_project_service.apis["sqladmin.googleapis.com"],
  ]

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.genesis.id
      enable_private_path_for_google_cloud_services = true
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
      }
    }

    maintenance_window {
      day          = 7
      hour         = 4
      update_track = "stable"
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "genesis" {
  name     = var.db_name
  instance = google_sql_database_instance.genesis.name
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "google_sql_user" "genesis_app" {
  name     = var.db_user
  instance = google_sql_database_instance.genesis.name
  password = random_password.db_password.result
}
