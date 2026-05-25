"""Phase 6: Credential Broker + Hot Rotation.

Demonstrates the MITRITY gateway substituting ${credential:<id>}
placeholders in outbound tool args using broker-resolved values. The
agent never sees the real credential — the gateway resolves it
between governance approval and forwarding to the upstream MCP tool.

What this phase shows:

  6a Substitution works — the agent calls api:connect_database with a
     literal `${credential:demo_db_password}` in the connection string;
     the gateway resolves it via the broker; the upstream tool sees the
     real password and returns its hash (which proves it received a
     real value, not the placeholder).

  6b Hot rotation — between two calls we ask the operator to rotate the
     credential in the MITRITY dashboard. The gateway picks up the new
     value on the next heartbeat (≤30s) without restarting the agent
     or the gateway. The second call's password hash differs from the
     first, proving the rotation propagated.

  6c Fail-closed semantics — the agent attempts to call
     api:connect_database with a non-existent credential ID. The gateway
     responds with `credential.unresolvable` and the upstream tool
     never receives the call.

REQUIRES backend config (see README):

  - A credential definition named "demo_db_password" in the tenant.
  - A grant for that credential to the demo agent with "read" operation.
  - credentials.injection_enabled: true in gateway.yaml (set by
    docker-compose.yml in this repo).

Without those, 6a/6b run as `credential.unresolvable` failures —
useful for testing the fail-closed path but not the substitution
itself.

Note: the gateway namespaces upstream tools (api:connect_database
rather than connect_database). The placeholder syntax is unchanged.
"""

import time

from output import info, pause


def run(agent) -> None:
    info("Demonstrating credential broker + hot rotation...")
    pause(1.0)

    # ── 6a Substitution works ──────────────────────────────────────────
    info("6a: api:connect_database with ${credential:demo_db_password} placeholder")
    agent.run_prompt(
        "Call the api:connect_database tool with this exact connection_string "
        "(verbatim — do not invent values, do not strip the placeholder):\n\n"
        "  postgres://app:${credential:demo_db_password}@db.internal:5432/orders\n\n"
        "The MITRITY gateway will substitute ${credential:demo_db_password} "
        "with the broker-resolved value before the tool receives the call. "
        "Report the password hash from the tool's response."
    )
    pause(2.0)

    # ── 6b Hot rotation ────────────────────────────────────────────────
    info(
        "6b: HOT ROTATION — open your MITRITY dashboard now, rotate "
        "demo_db_password (Credentials → demo_db_password → Rotate), "
        "then press Enter to continue. The gateway will pick up the new "
        "value on its next heartbeat (≤30s)."
    )
    try:
        input()  # nosec — interactive demo prompt, not security-sensitive
    except EOFError:
        info("(non-interactive mode — waiting 35s for heartbeat instead)")
        time.sleep(35)

    info("6b cont.: same call again — expect a different password hash")
    agent.run_prompt(
        "Call the api:connect_database tool again with the same connection_string "
        "as before:\n\n"
        "  postgres://app:${credential:demo_db_password}@db.internal:5432/orders\n\n"
        "Report the new password hash. It should differ from the previous "
        "one — proving the rotation propagated to the running gateway "
        "without restarting the agent."
    )
    pause(2.0)

    # ── 6c Fail-closed for unknown credential ──────────────────────────
    info("6c: api:connect_database with an unknown credential id (fail closed)")
    agent.run_prompt(
        "Call the api:connect_database tool with this connection string:\n\n"
        "  postgres://app:${credential:nonexistent_cred}@db.internal:5432/orders\n\n"
        "The gateway will refuse — there is no grant for that credential id "
        "on this agent — and the upstream tool will never receive the call. "
        "The error code is credential.unresolvable (JSON-RPC code -32002)."
    )
    pause(1.0)

    info(
        "Phase 6 complete. Audit the credential.used events in your "
        "MITRITY dashboard at /app/audit to confirm each resolve was "
        "recorded with the right agent_id and tool."
    )
