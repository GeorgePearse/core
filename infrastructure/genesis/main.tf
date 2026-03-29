terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  backend "gcs" {
    bucket = "genesis-tf-state-visdet-482415"
    prefix = "infrastructure/genesis/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
