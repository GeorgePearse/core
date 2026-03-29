terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "genesis-tf-state-visdet-482415"
    prefix = "infrastructure/plane/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_compute_network" "genesis" {
  name = "genesis-vpc"
}

data "google_compute_subnetwork" "genesis" {
  name   = "genesis-subnet"
  region = var.region
}
