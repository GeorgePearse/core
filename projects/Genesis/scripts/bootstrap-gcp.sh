#!/usr/bin/env bash
#
# Bootstrap Genesis infrastructure on GCP.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - terraform >= 1.5 installed
#   - You have Owner or Editor role on the project
#
# Usage:
#   ./scripts/bootstrap-gcp.sh
#
# After this script completes, it will print the GitHub secrets
# you need to configure at:
#   https://github.com/GeorgePearse/Genesis/settings/secrets/actions
#
set -euo pipefail

PROJECT_ID="visdet-482415"
REGION="europe-west2"
SA_NAME="genesis-bootstrap"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
STATE_BUCKET="genesis-tf-state-visdet-482415"
KEY_FILE="/tmp/genesis-gcp-sa-key.json"

echo "========================================="
echo " Genesis GCP Bootstrap"
echo " Project: ${PROJECT_ID}"
echo " Region:  ${REGION}"
echo "========================================="
echo ""

# -------------------------------------------
# Step 1: Set project
# -------------------------------------------
echo "[1/7] Setting project..."
gcloud config set project "${PROJECT_ID}"

# -------------------------------------------
# Step 2: Enable required APIs
# -------------------------------------------
echo "[2/7] Enabling GCP APIs (this may take a minute)..."
gcloud services enable \
  sqladmin.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  vpcaccess.googleapis.com \
  servicenetworking.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com \
  cloudresourcemanager.googleapis.com \
  containerregistry.googleapis.com

# -------------------------------------------
# Step 3: Create Terraform state bucket
# -------------------------------------------
echo "[3/7] Creating Terraform state bucket..."
if gcloud storage buckets describe "gs://${STATE_BUCKET}" &>/dev/null; then
  echo "  Bucket already exists, skipping."
else
  gcloud storage buckets create "gs://${STATE_BUCKET}" \
    --location="${REGION}" \
    --uniform-bucket-level-access
fi

# -------------------------------------------
# Step 4: Create bootstrap service account
# -------------------------------------------
echo "[4/7] Creating bootstrap service account..."
if gcloud iam service-accounts describe "${SA_EMAIL}" &>/dev/null 2>&1; then
  echo "  Service account already exists, skipping creation."
else
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Genesis Bootstrap SA"
fi

ROLES=(
  "roles/editor"
  "roles/iam.serviceAccountAdmin"
  "roles/iam.serviceAccountKeyAdmin"
  "roles/resourcemanager.projectIamAdmin"
  "roles/secretmanager.admin"
  "roles/storage.admin"
  "roles/servicenetworking.networksAdmin"
)

for ROLE in "${ROLES[@]}"; do
  echo "  Granting ${ROLE}..."
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet \
    --condition=None 2>/dev/null || true
done

echo "  Creating key file..."
if [ -f "${KEY_FILE}" ]; then
  echo "  Key file already exists at ${KEY_FILE}, reusing."
else
  gcloud iam service-accounts keys create "${KEY_FILE}" \
    --iam-account="${SA_EMAIL}"
fi

# -------------------------------------------
# Step 5: Terraform init and apply
# -------------------------------------------
echo "[5/7] Running Terraform..."
export GOOGLE_APPLICATION_CREDENTIALS="${KEY_FILE}"

cd "$(dirname "$0")/../terraform"

echo "  terraform init..."
terraform init

echo ""
echo "  terraform plan..."
terraform plan -out=tfplan \
  -var="openai_api_key=PLACEHOLDER_REPLACE_ME" \
  -var="anthropic_api_key=PLACEHOLDER_REPLACE_ME"

echo ""
echo "  About to apply. Review the plan above."
read -rp "  Proceed with terraform apply? [y/N] " confirm
if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
  echo "  Aborted."
  exit 1
fi

terraform apply tfplan
rm -f tfplan

# -------------------------------------------
# Step 6: Extract outputs
# -------------------------------------------
echo "[6/7] Extracting outputs..."
CLOUD_SQL_CONN=$(terraform output -raw cloud_sql_instance)
DB_PASSWORD=$(terraform output -raw db_password)
CLOUD_RUN_URL=$(terraform output -raw cloud_run_url)
GITHUB_SA=$(terraform output -raw github_actions_service_account)

cd - > /dev/null

# -------------------------------------------
# Step 7: Create key for GitHub Actions SA
# -------------------------------------------
echo "[7/7] Creating GitHub Actions SA key..."
GH_SA_KEY_FILE="/tmp/genesis-github-actions-key.json"
gcloud iam service-accounts keys create "${GH_SA_KEY_FILE}" \
  --iam-account="${GITHUB_SA}" 2>/dev/null || echo "  (key may already exist)"

echo ""
echo "========================================="
echo " Bootstrap complete!"
echo "========================================="
echo ""
echo " Cloud Run URL: ${CLOUD_RUN_URL}"
echo ""
echo " Next steps:"
echo ""
echo " 1. Seed your real API keys:"
echo "    echo -n 'sk-your-real-openai-key' | gcloud secrets versions add genesis-openai-api-key --data-file=-"
echo "    echo -n 'sk-ant-your-real-key'    | gcloud secrets versions add genesis-anthropic-api-key --data-file=-"
echo ""
echo " 2. Add these GitHub repo secrets at:"
echo "    https://github.com/GeorgePearse/Genesis/settings/secrets/actions"
echo ""
echo "    GCP_SA_KEY                  = contents of ${GH_SA_KEY_FILE}"
echo "    CLOUD_SQL_CONNECTION_NAME   = ${CLOUD_SQL_CONN}"
echo "    DB_NAME                     = genesis"
echo "    DB_USER                     = genesis_app"
echo "    DB_PASSWORD                 = ${DB_PASSWORD}"
echo ""
echo " 3. Push to main -- the CI/CD pipeline will build, migrate, and deploy."
echo ""
echo " 4. Clean up key files when done:"
echo "    rm -f ${KEY_FILE} ${GH_SA_KEY_FILE}"
echo ""
