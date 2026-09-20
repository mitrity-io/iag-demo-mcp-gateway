FROM --platform=linux/amd64 golang:1.26-alpine AS go-builder

WORKDIR /build
COPY go.mod ./
RUN go mod download
COPY cmd/ cmd/
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -trimpath -o /demo-tools ./cmd/demo-tools

# Pull the pre-built gateway binary from the public ghcr.io image.
FROM --platform=linux/amd64 ghcr.io/mitrity-io/mitrity-mcp-gateway:latest AS gateway

FROM --platform=linux/amd64 python:3.12-slim

# gettext-base: envsubst renders the gateway config in entrypoint.sh.
# ca-certificates: TLS to PyPI at build time and to the control plane at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=go-builder /demo-tools /usr/local/bin/demo-tools
COPY --from=gateway /mitrity-gateway /usr/local/bin/mitrity-gateway

COPY scenario/ /app/scenario/
COPY config/ /etc/mitrity/
COPY workspace/ /workspace/

# The Claude Agent SDK wheel bundles the Claude Code runtime; no Node.js needed.
RUN pip install --no-cache-dir -r /app/scenario/requirements.txt

# The MITRITY adapter from PyPI, pinned to a release. Override for another version:
# docker compose build --build-arg MITRITY_PYTHON_SPEC='mitrity[claude-agent-sdk]==X.Y.Z'.
ARG MITRITY_PYTHON_SPEC="mitrity[claude-agent-sdk]==0.2.0"
RUN pip install --no-cache-dir "$MITRITY_PYTHON_SPEC"

# The demo runs as an unprivileged user. uid 1000 is the usual first user on a
# Linux host, so the bind-mounted ./workspace stays writable there (Docker
# Desktop maps ownership itself). The gateway refuses an admission runtime
# directory it does not own, so /run/mitrity is created for this user before
# the switch (mode 0700; entrypoint.sh checks the ownership and re-asserts the
# mode). /etc/mitrity takes the rendered gateway.yaml, /workspace the agent's
# files and the gateway's transport key, and $HOME the Claude Code session state.
RUN groupadd --gid 1000 demo \
    && useradd --uid 1000 --gid demo --create-home demo \
    && mkdir -p /run/mitrity \
    && chmod 0700 /run/mitrity \
    && chown -R demo:demo /run/mitrity /etc/mitrity /workspace \
    && chmod +x /app/scenario/entrypoint.sh

WORKDIR /app
USER demo
ENV HOME=/home/demo

ENTRYPOINT ["/app/scenario/entrypoint.sh"]
