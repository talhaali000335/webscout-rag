#!/usr/bin/env bash
# Runs ON the EC2 server (called by the webhook listener, or by hand).
set -euo pipefail
cd /opt/webscout
set -a; source .env; set +a

git pull --ff-only || echo "git pull skipped"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

docker compose pull backend frontend
docker compose up -d --no-build --remove-orphans
docker image prune -f
echo "deployed OK $(date)"
