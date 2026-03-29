#!/bin/sh
set -e

# Validate required env vars.
for var in ANTHROPIC_API_KEY MITRITY_AGENT_KEY MITRITY_CONTROL_PLANE_URL MITRITY_AGENT_ID; do
    eval val=\$$var
    if [ -z "$val" ]; then
        echo "ERROR: $var is not set. See .env.example for required variables."
        exit 1
    fi
done

# Export gateway version for the demo runner.
MITRITY_GATEWAY_VERSION="$(/usr/local/bin/mitrity-gateway -version 2>/dev/null || echo "unknown")"
export MITRITY_GATEWAY_VERSION

# Render the gateway config template with env vars.
envsubst < /etc/mitrity/gateway.yaml.tmpl > /etc/mitrity/gateway.yaml

echo "Gateway config written to /etc/mitrity/gateway.yaml"

exec python /app/scenario/runner.py "$@"
