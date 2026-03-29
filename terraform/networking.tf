resource "google_compute_network" "genesis" {
  name                    = "genesis-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
}

resource "google_compute_subnetwork" "genesis" {
  name          = "genesis-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.genesis.id
}

resource "google_compute_global_address" "private_ip" {
  name          = "genesis-db-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.genesis.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.genesis.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]

  depends_on = [google_project_service.apis["servicenetworking.googleapis.com"]]
}

resource "google_vpc_access_connector" "genesis" {
  name          = "genesis-connector"
  region        = var.region
  network       = google_compute_network.genesis.name
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 3

  depends_on = [google_project_service.apis["vpcaccess.googleapis.com"]]
}
