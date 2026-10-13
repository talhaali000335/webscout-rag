#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 22.04/24.04 EC2 server.
# Usage:  sudo bash ec2-setup.sh https://github.com/YOU/webscout-rag.git
set -euo pipefail
REPO_URL="${1:?Pass your GitHub repo URL as the first argument}"

echo "== 1/6 swap file (t2.micro only has 1 GB RAM) =="
if [ ! -f /swapfile ]; then
  fallocate -l 3G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== 2/6 packages =="
apt-get update -y && apt-get install -y git curl unzip ca-certificates openssl

echo "== 3/6 Docker =="
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

echo "== 4/6 AWS CLI =="
if ! command -v aws >/dev/null; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscli.zip
  unzip -q /tmp/awscli.zip -d /tmp && /tmp/aws/install
fi

echo "== 5/6 get the code =="
[ -d /opt/webscout/.git ] || git clone "$REPO_URL" /opt/webscout
cd /opt/webscout
[ -f .env ] || cp .env.example .env

echo "== 6/6 webhook service =="
if [ ! -f deploy/webhook.env ]; then
  echo "WEBHOOK_SECRET=$(openssl rand -hex 24)" > deploy/webhook.env
  chmod 600 deploy/webhook.env
fi
cp deploy/webscout-webhook.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now webscout-webhook

echo
echo "DONE. Next:"
echo "  1) nano /opt/webscout/.env      (add GROQ_API_KEY, ECR_REGISTRY, AWS_REGION)"
echo "  2) Your WEBHOOK_SECRET (copy into the GitHub secret WEBHOOK_SECRET):"
grep WEBHOOK_SECRET deploy/webhook.env
