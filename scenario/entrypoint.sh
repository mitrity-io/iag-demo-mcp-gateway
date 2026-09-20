#!/bin/sh
set -e

# Validate required env vars.
for var in ANTHROPIC_API_KEY MITRITY_AGENT_KEY MITRITY_CONTROL_PLANE_URL MITRITY_AGENT_ID; do
    eval val=\$$var
    if [ -z "$val" ]; then
        echo "ERROR: $var is not set. See .env.example for required variables." >&2
        exit 1
    fi
done

# Export gateway version for the demo runner.
MITRITY_GATEWAY_VERSION="$(/usr/local/bin/mitrity-gateway -version 2>/dev/null || echo "unknown")"
export MITRITY_GATEWAY_VERSION

# Runtime directory for the admission socket and token. The image creates it
# owned by the demo user, mode 0700, and the gateway refuses a directory it does
# not own or that is group- or world-writable: anything that can bind the socket
# path could harvest the token and allow everything. Check rather than create,
# and check before anything is written, so a tmpfs on /run or a `user:` override
# in docker-compose.yml fails here with a message instead of a permission error
# further down.
RUNTIME_DIR=/run/mitrity
if [ ! -d "$RUNTIME_DIR" ]; then
    echo "ERROR: $RUNTIME_DIR does not exist. The image creates it for the container user;" \
        "if /run is mounted as tmpfs, create the directory there owned by uid $(id -u), mode 0700." >&2
    exit 1
fi
owner="$(stat -c '%u' "$RUNTIME_DIR")"
if [ "$owner" != "$(id -u)" ]; then
    echo "ERROR: $RUNTIME_DIR is owned by uid $owner, but the demo runs as uid $(id -u). The gateway" \
        "serves its admission API only from a directory it owns. If you set 'user:' in" \
        "docker-compose.yml, give that user the directory (chown, mode 0700) or drop the override." >&2
    exit 1
fi
chmod 0700 "$RUNTIME_DIR"
export MITRITY_ADMISSION_ADDR="unix:/run/mitrity/admission.sock"
export MITRITY_ADMISSION_TOKEN_FILE="/run/mitrity/admission.token"

# Render the gateway config template with env vars. The rendered file carries
# the agent key, so it is created readable by this user only: the umask covers
# the file the subshell creates, the chmod a file that already existed.
(umask 077 && envsubst < /etc/mitrity/gateway.yaml.tmpl > /etc/mitrity/gateway.yaml)
chmod 0600 /etc/mitrity/gateway.yaml

echo "Gateway config written to /etc/mitrity/gateway.yaml"

exec python /app/scenario/runner.py "$@"
