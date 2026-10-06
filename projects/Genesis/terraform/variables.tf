variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "visdet-482415"
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "europe-west2"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "genesis"
}

variable "db_user" {
  description = "PostgreSQL application user"
  type        = string
  default     = "genesis_app"
}

variable "cloud_run_image" {
  description = "Container image for backend Cloud Run (set by CI/CD; uses placeholder for initial bootstrap)"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "frontend_image" {
  description = "Container image for frontend Cloud Run (set by CI/CD; uses placeholder for initial bootstrap)"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "cloud_run_min_instances" {
  description = "Minimum Cloud Run instances"
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 3
}

variable "openai_api_key" {
  description = "OpenAI API key (initial seed; update via gcloud secrets)"
  type        = string
  sensitive   = true
  default     = "PLACEHOLDER_REPLACE_ME"
}

variable "anthropic_api_key" {
  description = "Anthropic API key (initial seed; update via gcloud secrets)"
  type        = string
  sensitive   = true
  default     = "PLACEHOLDER_REPLACE_ME"
}
