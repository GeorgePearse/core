variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "visdet-482415"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "europe-west2"
}

variable "zone" {
  description = "GCP zone for the VM"
  type        = string
  default     = "europe-west2-a"
}

variable "machine_type" {
  description = "GCE machine type (2 vCPU / 8 GB recommended minimum)"
  type        = string
  default     = "e2-standard-4"
}

variable "disk_size_gb" {
  description = "Boot disk size in GB"
  type        = number
  default     = 50
}

variable "plane_version" {
  description = "Vendored Plane CE git tag (must match the subtree in vendor/plane/)"
  type        = string
  default     = "v1.2.3"
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into the Plane VM (empty = no SSH access)"
  type        = list(string)
  default     = []
}
