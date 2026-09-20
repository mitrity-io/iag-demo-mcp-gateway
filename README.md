# MITRITY MCP Gateway — Governance Demo

Self-contained Docker demo that runs a [Claude Agent SDK](https://docs.claude.com/en/docs/agent-sdk) agent through a scripted governance scenario with the Mitrity Gateway on **both** of the agent's entrances:

- **MCP tools** (`fs__read_file`, `shell__run_command`, `api__call_api`, …) reach the model through the gateway, which the SDK starts as its MCP server. Every `tools/call` is evaluated against your MITRITY policies before the upstream tool sees it.
- **The SDK's own built-in tools** (`Bash`, `Write`, `Edit`) never produce an MCP call. The [`mitrity`](https://github.com/mitrity-io/mitrity-python) adapter installs a `PreToolUse` hook that admits each one through the gateway's loopback admission API before the SDK runs it — same rules, same command analysis, same DLP, same audit trail (`surface=agent_hook`). If the edge cannot be reached, the call is denied.

## Prerequisites

- Docker Desktop (or any Docker runtime)
- A MITRITY account with an active tenant
- An Anthropic API key

## Dashboard Setup

Before running the demo, configure these in your MITRITY dashboard:

### 1. Register an agent

Create an agent (e.g., "demo-agent") with mission scope "workspace file management and system operations". Copy the **Agent ID** and **Agent Key** (`ak_...`).

### 2. Create policies

Tool patterns name their surface: MCP tools served by the gateway are `mcp:<namespace>__<tool>` (the upstream's namespace and the tool name joined by a double underscore — `mcp:fs__read_file`), the SDK's built-in tools are `builtin:<tool>`.

| Policy | Type | Tool pattern | Scope |
|--------|------|--------------|-------|
| Allow workspace reads | allow | `mcp:fs__read_file`, `mcp:fs__list_directory` | path starts with `/workspace` |
| Allow workspace writes | allow | `mcp:fs__write_file` | path starts with `/workspace` |
| Allow safe commands | allow | `mcp:shell__run_command` | resolved commands `ls`, `pwd`, `cat`, `echo`, `whoami` |
| Block system files | deny | `mcp:fs__read_file`, `mcp:fs__delete_file` | path outside `/workspace` |
| Block destructive commands | deny | `mcp:shell__run_command` | resolved commands `rm`, `curl`, `wget`, `nc`, `chmod` |
| Block dangerous SQL | deny | `mcp:api__query_database` | contains `DROP`, `DELETE`, `TRUNCATE` |
| Hold production deploys | hold | `mcp:api__call_api` | url contains "production" |
| Block destructive built-ins (phase 8) | deny | `builtin:bash` | resolved commands `rm`, `curl`, `wget`, `nc`, `chmod` |

Also enable:
- **Prompt injection detection** (global setting)
- **DLP** with PII and credential patterns — DLP applies to `builtin:write` content with no extra rule.

> **Upgrading from an earlier version of this demo?** Tools used to be served as `fs:read_file`, `shell:run_command`, `api:call_api`. Claude Code exposes MCP tools to the model as `mcp__<server>__<tool>`, and the Anthropic API accepts tool names matching `^[a-zA-Z0-9_-]{1,128}$` only, so a colon could never be called from the Agent SDK. The gateway now joins namespace and tool with a double underscore (`fs__read_file`); recreate the policies above with `mcp:<namespace>__<tool>` patterns.

### 3. Phase 9 (optional): route built-in Bash into the governed shell

Set the policy knob **`builtin_exec_routing: governed_shell`** on the agent's policy. Requires a gateway from **sentinel ≥ v0.21.0** (the `exec` tool source, `POST /v1/exec` and the `mitrity-hook exec` relay), `exec.enabled: true` in `gateway.yaml`, and the `mitrity-hook` binary inside the container. Until `ghcr.io/mitrity-io/mitrity-mcp-gateway:latest` carries the governed shell, phase 9 prints what it will demonstrate and skips.

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

> The image installs the adapter from PyPI, pinned to `mitrity[claude-agent-sdk]==0.2.0` (see `MITRITY_PYTHON_SPEC` in the Dockerfile). Another version is one build argument away: `docker compose build --build-arg MITRITY_PYTHON_SPEC='mitrity[claude-agent-sdk]==X.Y.Z'`.

## What the Demo Does

The demo runs eight phases (~15 minutes total):

**Phase 1 — Normal Operations**: The agent reads files, lists directories, runs safe commands, and calls APIs. All actions are allowed through the gateway.

**Phase 2 — Policy Violations**: The agent attempts to read system files (`/etc/passwd`), run destructive commands (`rm -rf`, `curl`), and execute dangerous SQL (`DROP TABLE`). The gateway blocks each action and returns the policy reason.

**Phase 3 — Prompt Injection**: The agent processes "user input" containing embedded injection payloads. The gateway's injection detection catches and blocks the attacks.

**Phase 4 — DLP & Data Protection**: The agent tries to write files containing API keys, send notifications with PII (SSNs, credit cards), and include credentials in API calls. The gateway's DLP engine blocks data exfiltration.

**Phase 5 — Escalation & Hold**: The agent attempts a production deployment. The gateway's hold policy pauses the action and creates an approval request in your MITRITY dashboard.

**Phase 6 — Credential Broker + Hot Rotation**: The agent calls `connect_database` with `${credential:demo_db_password}` in the connection string. The gateway resolves the placeholder via the broker; the upstream tool returns the password hash. Mid-phase, you rotate the credential in the dashboard — the next call picks up the new value within 30 seconds with no agent or gateway restart. Requires backend setup (see below). The `${credential:nonexistent_cred}` sub-step demonstrates fail-closed behavior.

**Phase 8 — Built-in Tools (admission hook)**: The agent uses the SDK's *own* `Bash` and `Write` tools instead of the MCP tools. An allowed `ls` runs; `rm -rf` is denied with the policy reason; the same command hidden behind `bash -c '…'` is still denied, because the edge parses the command tree rather than matching the first word; a `.env` file full of AWS and Stripe keys written with `Write` is blocked by DLP before it exists. Every decision is an audit row with `surface=agent_hook`.

**Phase 9 — Governed Shell**: With `builtin_exec_routing: governed_shell`, an allowed built-in `Bash` is not executed by the SDK at all: the hook rewrites it to `mitrity-hook exec <ticket>`, the gateway runs the judged bytes in its own sandbox, and egress to a host outside the agent's destination allowlist is refused by the governed shell's proxy. The audit event carries `execution_result.sandbox_mode` and the egress counters. *Requires sentinel ≥ v0.21.0*; skipped with a notice on older gateways.

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

If you skip this setup, Phase 6 runs the fail-closed path only — `connect_database` calls return `credential.unresolvable` (JSON-RPC -32002) and the upstream tool never sees them. Phases 1–5 are unaffected.

## Architecture

```
Docker Container
└── Python scenario runner (Claude Agent SDK, ClaudeSDKClient)
    ├── built-in tools: Bash, Write, Edit ── PreToolUse hook (mitrity adapter)
    │                                          └── POST /v1/admit ──► admission API (unix:/run/mitrity/admission.sock)
    └── MCP server "mitrity" = Mitrity Gateway (stdio)
        ├── upstream "filesystem" (namespace fs): fs__read_file, fs__write_file, fs__list_directory, fs__delete_file
        ├── upstream "shell" (namespace shell): shell__run_command
        └── upstream "api" (namespace api): api__call_api, api__query_database, api__send_notification, api__connect_database
                             ↳ Phase 6 — broker-substituted credential
```

One gateway process serves both entrances: the MCP `tools/call` stream from the SDK and the loopback admission API the hook calls. It connects to your MITRITY control plane over HTTPS for policy evaluation, event reporting and heartbeat, and attests the runtime's posture (which built-in tools are hooked, which are not, other MCP servers, permission mode) so the dashboard can show honest coverage.

The adapter is `mitrity.claude_agent_sdk.Governor` — see [`scenario/runner.py`](scenario/runner.py) for the ~20 lines that wire it up, and [iag-specs/sentinel/adapters.md](https://github.com/mitrity-io/iag-specs/blob/main/sentinel/adapters.md) for what it guarantees.

## Gateway vs Sidecar

Both binaries share the same governance core. Threat intelligence, delegation chains, DLP, prompt injection detection, ML drift scoring, hold/approval workflows, and credential broker injection all run identically in either deployment — they're implemented in a shared `internal/interceptor` package. The architectural difference is **where each sits in the MCP request path**:

| | Mitrity Gateway (this demo) | [MCP Sidecar](https://github.com/mitrity-io/iag-demo-mcp-sidecar) |
|---|---|---|
| **Role** | Is the MCP server, aggregating many sources | Transparent proxy in front of one existing MCP server |
| **Tool sources** | Multiple upstreams + native HTTP tools defined in config | Single upstream subprocess |
| **MCP protocol** | Owns the catalog; prefixes upstream tools with a namespace (`fs__read_file`) | Passes through unchanged; intercepts only `tools/call` |
| **Admission API** | Served alongside the MCP surface (this demo's phase 8) | Served alongside the proxy |
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
| `ANTHROPIC_MODEL` | No | Claude model (default: `claude-sonnet-5`) |
| `MITRITY_DEMO_FORCE_PHASE9` | No | `1` runs phase 9 even when the gateway version does not advertise the governed shell |

## Customization

- **Workspace**: Mount your own files via `volumes` in `docker-compose.yml`
- **Policies**: Modify policies in the MITRITY dashboard to see different behaviors
- **Scenarios**: Edit files in `scenario/phases/` to add custom test prompts
