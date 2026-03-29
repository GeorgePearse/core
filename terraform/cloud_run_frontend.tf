resource "google_cloud_run_v2_service" "genesis_frontend" {
  name     = "genesis-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.frontend_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }

      env {
        name  = "BACKEND_URL"
        value = google_cloud_run_v2_service.genesis.uri
      }
    }
  }

  depends_on = [
    google_cloud_run_v2_service.genesis,
    google_project_service.apis["run.googleapis.com"],
  ]
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.genesis_frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
