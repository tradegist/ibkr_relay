#!/usr/bin/env bash
# Place an order via the remote-client HTTP API running on the droplet.
#
# Usage:
#   ./order.sh  2 TSLA MKT          # buy 2 shares market
#   ./order.sh -2 TSLA MKT          # sell 2 shares market
#   ./order.sh  2 TSLA LMT 352.5    # buy 2 shares limit $352.5
#   ./order.sh -2 TSLA LMT 380      # sell 2 shares limit $380

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <quantity> <symbol> <MKT|LMT> [limitPrice]"
  echo "  Positive quantity = BUY, negative = SELL"
  exit 1
fi

QTY="$1"
SYMBOL="$2"
ORDER_TYPE="$(echo "$3" | tr '[:lower:]' '[:upper:]')"

# Get droplet IP from terraform
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DROPLET_IP=$(cd "$SCRIPT_DIR/terraform" && terraform output -raw droplet_ip 2>/dev/null)

if [[ -z "$DROPLET_IP" ]]; then
  echo "Error: Could not get droplet IP from terraform output"
  exit 1
fi

SSH_KEY="$HOME/.ssh/ibkr-relay"

# Build JSON payload
if [[ "$ORDER_TYPE" == "LMT" ]]; then
  if [[ $# -lt 4 ]]; then
    echo "Error: limitPrice required for LMT orders"
    exit 1
  fi
  LIMIT_PRICE="$4"
  JSON=$(printf '{"quantity":%s,"symbol":"%s","orderType":"LMT","limitPrice":%s}' "$QTY" "$SYMBOL" "$LIMIT_PRICE")
elif [[ "$ORDER_TYPE" == "MKT" ]]; then
  JSON=$(printf '{"quantity":%s,"symbol":"%s","orderType":"MKT"}' "$QTY" "$SYMBOL")
else
  echo "Error: orderType must be MKT or LMT (got: $ORDER_TYPE)"
  exit 1
fi

ACTION="BUY"
[[ "$QTY" -lt 0 ]] && ACTION="SELL"
ABS_QTY="${QTY#-}"

echo "Placing order: $ACTION $ABS_QTY $SYMBOL $ORDER_TYPE${LIMIT_PRICE:+ @ \$$LIMIT_PRICE}"

# Post to the HTTP API via the webhook-relay container.
# We pipe the JSON as stdin to avoid shell-quoting issues across SSH + docker exec.
RESPONSE=$(echo "$JSON" | ssh -i "$SSH_KEY" "root@$DROPLET_IP" \
  "docker compose -f /opt/ibkr-relay/docker-compose.yml exec -T webhook-relay \
   python -c 'import urllib.request,sys,json; d=sys.stdin.read(); req=urllib.request.Request(\"http://localhost:5000/order\",data=d.encode(),headers={\"Content-Type\":\"application/json\"},method=\"POST\"); resp=urllib.request.urlopen(req,timeout=15); print(resp.read().decode())'" 2>&1)

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
