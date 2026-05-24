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

The demo runs seven phases (~15 minutes total):

**Phase 1 — Normal Operations**: The agent reads files, lists directories, runs safe commands, and calls APIs. All actions are allowed through the gateway.

**Phase 2 — Policy Violations**: The agent attempts to read system files (`/etc/passwd`), run destructive commands (`rm -rf`, `curl`), and execute dangerous SQL (`DROP TABLE`). The gateway blocks each action and returns the policy reason.

**Phase 3 — Prompt Injection**: The agent processes "user input" containing embedded injection payloads. The gateway's injection detection catches and blocks the attacks.

**Phase 4 — DLP & Data Protection**: The agent tries to write files containing API keys, send notifications with PII (SSNs, credit cards), and include credentials in API calls. The gateway's DLP engine blocks data exfiltration.

**Phase 5 — Escalation & Hold**: The agent attempts a production deployment. The gateway's hold policy pauses the action and creates an approval request in your MITRITY dashboard.

**Phase 6 — Delegation Chains**: The agent records a series of agent-to-agent delegation hops via the `delegate` tool. The gateway's delegation engine flags depth violations (chains > 5 hops) and circular delegation (an agent appearing twice in a chain). Unauthorized-delegate and privilege-escalation sub-scenarios require additional per-agent backend configuration (`disallowed_delegates`, additional registered agents with broader `tool_permissions`); without it those sub-scenarios run as clean delegations. Open `/app/delegation-chains` in the dashboard to inspect.

**Phase 7 — Threat Intelligence**: The agent triggers actions that match threat-intelligence indicators (file reads, shell commands, API calls). The gateway evaluates each match against the tenant's per-severity policy and per-indicator overrides (block / alert / log / silent-suppress). Requires the demo tenant to be subscribed to a threat-indicator feed containing matching patterns; without that seed config the actions appear in the audit log with no threat matches. Open `/app/threat-intel` (Matches + Landscape tabs) to inspect.

## Architecture

```
Docker Container
└── Python scenario runner (Claude Agent SDK)
    └── Mitrity Gateway (MCP server, governed)
        ├── upstream "fs": filesystem tools (read, write, list, delete)
        ├── upstream "shell": command execution
        ├── upstream "api": mock API/database/notification tools
        └── upstream "delegate": multi-agent delegation tool (Phase 6)
```

The gateway connects to your MITRITY control plane via HTTPS for policy evaluation, event reporting, and heartbeat.

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
