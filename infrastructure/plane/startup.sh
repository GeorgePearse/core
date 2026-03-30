#!/usr/bin/env bash
set -euo pipefail

MARKER="/opt/plane/.installed"
if [[ -f "$MARKER" ]]; then
  echo "Plane already installed, skipping startup script."
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

# Install Docker
apt-get update -y
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker

# Create Plane data directory
mkdir -p /opt/plane
cd /opt/plane

# Run the Plane Community Edition installer in silent mode
# This downloads prime-cli, which pulls docker-compose.yml and starts services
curl -fsSL https://prime.plane.so/install/ | bash -s -- --silent

touch "$MARKER"
echo "Plane Community Edition installation complete."
