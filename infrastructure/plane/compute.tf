resource "google_service_account" "plane" {
  account_id   = "plane-vm"
  display_name = "Plane VM Service Account"
}

resource "google_project_iam_member" "plane_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.plane.email}"
}

resource "google_project_iam_member" "plane_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.plane.email}"
}

resource "google_compute_address" "plane" {
  name   = "plane-external-ip"
  region = var.region
}

resource "google_compute_instance" "plane" {
  name         = "plane-ce"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["plane-web", "plane-ssh"]

  boot_disk {
    initialize_params {
      image = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-ssd"
    }
  }

  network_interface {
    subnetwork = data.google_compute_subnetwork.genesis.id

    access_config {
      nat_ip = google_compute_address.plane.address
    }
  }

  metadata = {
    startup-script = replace(
      file("${path.module}/startup.sh"),
      "__DEPLOY_BUCKET__",
      google_storage_bucket.plane_deploy.name,
    )
  }

  service_account {
    email  = google_service_account.plane.email
    scopes = ["cloud-platform"]
  }

  allow_stopping_for_update = true

  lifecycle {
    ignore_changes = [metadata["startup-script"]]
  }
}
