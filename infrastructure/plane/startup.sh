#!/usr/bin/env bash
set -euo pipefail

MARKER="/opt/plane/.installed"
PLANE_DIR="/opt/plane"
DEPLOY_BUCKET="__DEPLOY_BUCKET__"
DEPLOY_OBJECT="plane-deploy.tar.gz"

if [[ -f "$MARKER" ]]; then
  echo "Plane already installed, skipping startup script."
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

# ── Install Docker ───────────────────────────────────────────────────
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

# ── Download vendored Plane source from GCS ──────────────────────────
mkdir -p "$PLANE_DIR"
cd "$PLANE_DIR"

echo "Downloading deploy artifact from gs://${DEPLOY_BUCKET}/${DEPLOY_OBJECT} ..."
curl -fsSL -o "${DEPLOY_OBJECT}" \
  "https://storage.googleapis.com/${DEPLOY_BUCKET}/${DEPLOY_OBJECT}"

tar xzf "${DEPLOY_OBJECT}"
rm -f "${DEPLOY_OBJECT}"

# ── Prepare environment files ────────────────────────────────────────
# The tarball contains:
#   plane/          – vendored Plane CE source (from vendor/plane/)
#   overrides/      – docker-compose.prod.yml and .env.template
#
# If no .env exists yet, seed from the template.
if [[ ! -f plane/.env ]]; then
  cp overrides/.env.template plane/.env
  echo "WARNING: Using default .env – update secrets before production use."
fi

# The API also needs its own .env; seed from the example if missing.
if [[ ! -f plane/apps/api/.env ]]; then
  cp plane/apps/api/.env.example plane/apps/api/.env
  echo "WARNING: Using default apps/api/.env – update secrets before production use."
fi

# ── Build and start services ─────────────────────────────────────────
cd plane

docker compose \
  -f docker-compose.yml \
  -f /opt/plane/overrides/docker-compose.prod.yml \
  up -d --build

touch "$MARKER"
echo "Plane Community Edition (vendored) installation complete."
