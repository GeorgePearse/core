output "plane_external_ip" {
  description = "External IP address of the Plane VM"
  value       = google_compute_address.plane.address
}

output "plane_url" {
  description = "URL to access Plane (configure DNS to point to the external IP)"
  value       = "http://${google_compute_address.plane.address}"
}

output "ssh_command" {
  description = "SSH into the Plane VM"
  value       = "gcloud compute ssh plane-ce --zone=${var.zone} --project=${var.project_id}"
}

output "plane_deploy_bucket" {
  description = "GCS bucket for Plane deploy artifacts (upload plane-deploy.tar.gz here)"
  value       = google_storage_bucket.plane_deploy.name
}

output "plane_version" {
  description = "Vendored Plane CE version"
  value       = var.plane_version
}
