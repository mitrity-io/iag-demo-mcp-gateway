FROM --platform=linux/amd64 golang:1.26-alpine AS go-builder

WORKDIR /build
COPY go.mod ./
RUN go mod download
COPY cmd/ cmd/
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -trimpath -o /demo-tools ./cmd/demo-tools

# Pull the pre-built gateway binary from the public ghcr.io image.
FROM --platform=linux/amd64 ghcr.io/mitrity-io/mitrity-mcp-gateway:latest AS gateway

FROM --platform=linux/amd64 python:3.12-slim

# git: the mitrity adapter is installed from its git repository until the
# first PyPI release (see scenario/requirements.txt).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=go-builder /demo-tools /usr/local/bin/demo-tools
COPY --from=gateway /mitrity-gateway /usr/local/bin/mitrity-gateway

COPY scenario/ /app/scenario/
COPY config/ /etc/mitrity/
COPY workspace/ /workspace/

# The Claude Agent SDK wheel bundles the Claude Code runtime; no Node.js needed.
RUN pip install --no-cache-dir -r /app/scenario/requirements.txt

# The MITRITY adapter. Until the first PyPI release this is a pinned git ref of
# github.com/mitrity-io/mitrity-python; swap it for `mitrity[claude-agent-sdk]==<version>`
# once published (docker compose build --build-arg MITRITY_PYTHON_SPEC=...).
ARG MITRITY_PYTHON_SPEC="mitrity[claude-agent-sdk] @ git+https://github.com/mitrity-io/mitrity-python.git@main"
RUN pip install --no-cache-dir "$MITRITY_PYTHON_SPEC"

# Runtime directory for the admission socket and token (mode 0700, see entrypoint.sh).
RUN mkdir -p /run/mitrity && chmod 0700 /run/mitrity

WORKDIR /app
RUN chmod +x /app/scenario/entrypoint.sh

ENTRYPOINT ["/app/scenario/entrypoint.sh"]
