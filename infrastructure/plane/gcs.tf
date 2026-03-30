resource "google_storage_bucket" "plane_deploy" {
  name     = "plane-deploy-${var.project_id}"
  location = var.region

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "plane_vm_reader" {
  bucket = google_storage_bucket.plane_deploy.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.plane.email}"
}
