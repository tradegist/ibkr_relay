#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# poll-now.sh — Trigger an immediate Flex poll on the droplet
# ---------------------------------------------------------------------------

DROPLET_IP=$(cd "$(dirname "$0")/terraform" && terraform output -raw droplet_ip 2>/dev/null) || true

if [[ -z "${DROPLET_IP:-}" ]]; then
  echo "Error: Could not read droplet IP from Terraform state." >&2
  echo "Usage: Pass it manually:  DROPLET_IP=1.2.3.4 ./poll-now.sh" >&2
  exit 1
fi

echo "Triggering immediate poll on $DROPLET_IP ..."
ssh -i ~/.ssh/ibkr-relay "root@$DROPLET_IP" \
  'cd /opt/ibkr-relay && docker compose exec -T poller python poller.py --once'
