resource "google_artifact_registry_repository" "genesis" {
  location      = var.region
  repository_id = "genesis"
  format        = "DOCKER"
  description   = "Genesis backend container images"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"

    most_recent_versions {
      keep_count = 10
    }
  }

  depends_on = [google_project_service.apis["artifactregistry.googleapis.com"]]
}
