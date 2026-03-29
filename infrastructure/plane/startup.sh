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

# Download Plane Community Edition setup files
curl -fsSL -o setup.sh https://prime.plane.so/install/
chmod +x setup.sh

# Run the installer in non-interactive mode
# The installer downloads docker-compose.yml and variables.env, then starts services
bash setup.sh --install

touch "$MARKER"
echo "Plane Community Edition installation complete."
