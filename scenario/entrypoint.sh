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

# Runtime directory for the admission socket and token. The Dockerfile creates
# it owned by the demo user; this only re-asserts mode 0700. The gateway refuses
# a directory it does not own or that is group- or world-writable: anything
# that can bind the socket path could harvest the token and allow everything.
mkdir -p /run/mitrity
chmod 0700 /run/mitrity
export MITRITY_ADMISSION_ADDR="unix:/run/mitrity/admission.sock"
export MITRITY_ADMISSION_TOKEN_FILE="/run/mitrity/admission.token"

exec python /app/scenario/runner.py "$@"
