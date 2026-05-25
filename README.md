# MITRITY MCP Gateway — Governance Demo

Self-contained Docker demo that runs a Claude-powered AI agent through a scripted governance scenario using the Mitrity Gateway. Every tool call is intercepted and evaluated against your MITRITY policies in real-time.

## Prerequisites

- Docker Desktop (or any Docker runtime)
- A MITRITY account with an active tenant
- An Anthropic API key

## Dashboard Setup

Before running the demo, configure these in your MITRITY dashboard:

### 1. Register an agent

Create an agent (e.g., "demo-agent") with mission scope "workspace file management and system operations". Copy the **Agent ID** and **Agent Key** (`ak_...`).

### 2. Create policies

| Policy | Type | Pattern | Scope |
|--------|------|---------|-------|
| Allow workspace reads | allow | `fs:read_file` | path starts with `/workspace` |
| Allow workspace writes | allow | `fs:write_file` | path starts with `/workspace` |
| Allow safe commands | allow | `shell:run_command` | `ls`, `pwd`, `cat`, `echo`, `whoami` |
| Block system files | deny | `fs:read_file`, `fs:delete_file` | path outside `/workspace` |
| Block destructive commands | deny | `shell:run_command` | `rm`, `curl`, `wget`, `nc`, `chmod` |
| Block dangerous SQL | deny | `api:query_database` | contains `DROP`, `DELETE`, `TRUNCATE` |
| Hold production deploys | hold | `api:call_api` | url contains "production" |

Also enable:
- **Prompt injection detection** (global setting)
- **DLP** with PII and credential patterns

## Quick Start

```bash
# Clone and configure
git clone git@github.com:mitrity-io/iag-demo-mcp-gateway.git
cd iag-demo-mcp-gateway
cp .env.example .env

# Edit .env with your API keys and IDs
# ANTHROPIC_API_KEY=sk-ant-...
# MITRITY_AGENT_ID=<uuid>
# MITRITY_AGENT_KEY=ak_...
# MITRITY_CONTROL_PLANE_URL=https://api.mitrity.com

# Run the demo
docker compose up --build
```

## What the Demo Does

The demo runs six phases (~12 minutes total):

**Phase 1 — Normal Operations**: The agent reads files, lists directories, runs safe commands, and calls APIs. All actions are allowed through the gateway.

**Phase 2 — Policy Violations**: The agent attempts to read system files (`/etc/passwd`), run destructive commands (`rm -rf`, `curl`), and execute dangerous SQL (`DROP TABLE`). The gateway blocks each action and returns the policy reason.

**Phase 3 — Prompt Injection**: The agent processes "user input" containing embedded injection payloads. The gateway's injection detection catches and blocks the attacks.

**Phase 4 — DLP & Data Protection**: The agent tries to write files containing API keys, send notifications with PII (SSNs, credit cards), and include credentials in API calls. The gateway's DLP engine blocks data exfiltration.

**Phase 5 — Escalation & Hold**: The agent attempts a production deployment. The gateway's hold policy pauses the action and creates an approval request in your MITRITY dashboard.

**Phase 6 — Credential Broker + Hot Rotation**: The agent calls `api:connect_database` with `${credential:demo_db_password}` in the connection string. The gateway resolves the placeholder via the broker; the upstream tool returns the password hash. Mid-phase, you rotate the credential in the dashboard — the next call picks up the new value within 30 seconds with no agent or gateway restart. Requires backend setup (see below). The `${credential:nonexistent_cred}` sub-step demonstrates fail-closed behavior.

> **Delegation chains and threat intelligence** are demonstrated in a separate, multi-container demo at [iag-demo-multi-agent](https://github.com/mitrity-io/iag-demo-multi-agent). That demo runs three governed agents in parallel containers (orchestrator + two workers) and produces real worker-to-worker delegation hops and threat-intel matches against the built-in indicator catalog. Pro/Enterprise plan required.

### Phase 6 prerequisites (credential broker)

Before running the demo, provision a credential in your tenant:

1. Open the MITRITY dashboard at `mitrity.com/app/credentials`.
2. Click **+ New Credential**:
   - **Name**: `demo_db_password`
   - **Type**: `db_password`
   - **Value**: any string (e.g., `s3cret-initial`)
   - **Max TTL**: 30 minutes
3. Click **+ Grant** on the credential and grant it to your demo agent with operation `read`.

Phase 6's mid-scenario rotation step asks you to rotate the credential in the dashboard. Click the credential, then **Rotate Value**, enter a new value (e.g., `s3cret-rotated`), and save. Press Enter in the demo to continue — the next call should show a different password hash within 30 seconds.

If you skip this setup, Phase 6 runs the fail-closed path only — `api:connect_database` calls return `credential.unresolvable` (JSON-RPC -32002) and the upstream tool never sees them. Phases 1–5 are unaffected.

## Architecture

```
Docker Container
└── Python scenario runner (Claude Agent SDK)
    └── Mitrity Gateway (MCP server, governed)
        ├── upstream "fs": filesystem tools (read, write, list, delete)
        ├── upstream "shell": command execution
        └── upstream "api": mock API/database/notification tools
                              ↳ includes connect_database (Phase 6 — broker-substituted credential)
```

The gateway connects to your MITRITY control plane via HTTPS for policy evaluation, event reporting, and heartbeat.

## Gateway vs Sidecar

Both binaries share the same governance core. Threat intelligence, delegation chains, DLP, prompt injection detection, ML drift scoring, hold/approval workflows, and credential broker injection all run identically in either deployment — they're implemented in a shared `internal/interceptor` package. The architectural difference is **where each sits in the MCP request path**:

| | Mitrity Gateway (this demo) | [MCP Sidecar](https://github.com/mitrity-io/iag-demo-mcp-sidecar) |
|---|---|---|
| **Role** | Is the MCP server, aggregating many sources | Transparent proxy in front of one existing MCP server |
| **Tool sources** | Multiple upstreams + native HTTP tools defined in config | Single upstream subprocess |
| **MCP protocol** | Owns the catalog, applies namespace prefixes (`fs:read_file`, `shell:run_command`) | Passes through unchanged; intercepts only `tools/call` |
| **Credential injection** | Arg-rewrite + file mounts + native HTTP headers/URL/body | Arg-rewrite + file mounts |
| **Best for** | Aggregating many tool sources behind one governed endpoint | Retrofitting governance onto an existing MCP server without changing the agent |

> **Credential broker injection** is **shipped on both binaries** with hot rotation. Both honor heartbeat-etag invalidation so a credential rotated in the dashboard propagates to the running wrapper within 30 seconds without restarting the agent. See [Phase 6 prerequisites](#phase-6-prerequisites-credential-broker) above for the live walkthrough, or [credential-injection-plan-2026-05-25.md](https://github.com/mitrity-io/iag-config/blob/main/credential-injection-plan-2026-05-25.md) for the contract.

> **Multi-agent governance?** See [iag-demo-multi-agent](https://github.com/mitrity-io/iag-demo-multi-agent) for a three-container compose stack showing real agent-to-agent delegation, per-agent threat intel, and per-agent credential scoping.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `MITRITY_AGENT_ID` | Yes | Agent UUID from dashboard |
| `MITRITY_AGENT_KEY` | Yes | Agent key (`ak_...`) from dashboard |
| `MITRITY_CONTROL_PLANE_URL` | Yes | Control plane URL (e.g., `https://api.mitrity.com`) |
| `MITRITY_DEMO_SPEED` | No | `normal` (default) or `fast` (skip pauses) |
| `ANTHROPIC_MODEL` | No | Claude model (default: `claude-sonnet-4-20250514`) |

## Customization

- **Workspace**: Mount your own files via `volumes` in `docker-compose.yml`
- **Policies**: Modify policies in the MITRITY dashboard to see different behaviors
- **Scenarios**: Edit files in `scenario/phases/` to add custom test prompts
