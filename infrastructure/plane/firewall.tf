resource "google_compute_firewall" "plane_web" {
  name    = "plane-allow-web"
  network = data.google_compute_network.genesis.id

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["plane-web"]
}

resource "google_compute_firewall" "plane_ssh" {
  count = length(var.allowed_ssh_cidrs) > 0 ? 1 : 0

  name    = "plane-allow-ssh"
  network = data.google_compute_network.genesis.id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.allowed_ssh_cidrs
  target_tags   = ["plane-ssh"]
}
