"""Phase 6: Delegation Chains — multi-agent governance.

Each sub-scenario invokes the `delegate` tool one or more times. The gateway
intercepts the calls and runs them through the delegation engine. The
audience watches the result land on the dashboard at /app/delegation-chains.

The agent IDs below are the deterministic UUIDs created by
iag-admin-backend `scripts/seed-demo.sql` (tier=demo). The backend's
ingest path requires valid UUIDs for delegator_agent_id / to_agent_id;
friendly names like "demo-rogue" wouldn't parse. The 6b intermediate
"hN" hops use synthetic UUIDs that don't need to exist as agents —
the chain_depth violation fires off the count, not the agent records.

Sub-scenarios:

  6a Clean delegation       — a simple two-hop chain that should be allowed.
  6b Depth exceeded         — chain of 6 hops, exceeds the default
                              max_chain_depth=5; the 6th hop blocks.
  6c Circular delegation    — same agent appears twice in the chain.
  6d Unauthorized delegate  — demo-rogue is in demo-primary's
                              disallowed_delegates per seed-demo.
  6e Privilege escalation   — demo-root has broader tool_permissions
                              than demo-primary per seed-demo; the
                              backend resolver computes the diff at
                              ingest.

All five sub-scenarios fire end-to-end once the demo tenant has been
seeded with `tier=demo` after the standard `tier=pro` seed. Without
the demo seed, 6d/6e fall back to clean delegations.
"""

import time

from output import info, pause


# ── Seeded agent UUIDs (must match iag-admin-backend/scripts/seed-demo.sql)
DEMO_PRIMARY   = "d0000003-0001-4000-a000-000000000001"
DEMO_ANALYTICS = "d0000003-0001-4000-a000-000000000002"
DEMO_ROGUE     = "d0000003-0001-4000-a000-000000000003"
DEMO_ROOT      = "d0000003-0001-4000-a000-000000000004"

# Synthetic hop UUIDs for the 6b deep-chain demo. These don't need to
# correspond to real agents — the depth check fires off hop count.
HOP_PREFIX = "d0000003-9001-4000-a000-00000000000"  # append digit 1-6


def _chain_id(label: str) -> str:
    """Stable-ish chain ID per demo run. Including the timestamp keeps
    chains distinct across repeated runs without making them
    completely random — easier to find in the dashboard right after a
    run.
    """
    return f"demo-{label}-{int(time.time())}"


def run(agent) -> None:
    info("Demonstrating delegation chain governance...")
    pause(1.0)

    # ── 6a Clean delegation ────────────────────────────────────────────
    info("6a: Clean two-hop delegation (should be allowed)")
    chain = _chain_id("clean")
    agent.run_prompt(
        "Delegate the order-total computation to the analytics agent. "
        f"Use the delegate tool with these exact arguments:\n"
        f"  delegation_chain_id = '{chain}'\n"
        f"  delegator_agent_id = '{DEMO_PRIMARY}'\n"
        f"  delegator_agent_name = 'demo-primary'\n"
        f"  delegator_mission_scope = 'workspace operations'\n"
        f"  to_agent_id = '{DEMO_ANALYTICS}'\n"
        f"  to_agent_name = 'demo-analytics'\n"
        f"  task = 'Compute today\\'s order total'"
    )
    pause(2.0)

    # ── 6b Depth exceeded ──────────────────────────────────────────────
    # Six hops on the same chain_id. The 6th exceeds the default
    # max_chain_depth=5 and the backend's hop-violation resolver flags
    # it as depth_exceeded.
    info("6b: Chain of 6 hops exceeding the default depth limit (=5)")
    chain = _chain_id("deep")
    hop_pairs = [
        (DEMO_PRIMARY, f"{HOP_PREFIX}1"),
        (f"{HOP_PREFIX}1", f"{HOP_PREFIX}2"),
        (f"{HOP_PREFIX}2", f"{HOP_PREFIX}3"),
        (f"{HOP_PREFIX}3", f"{HOP_PREFIX}4"),
        (f"{HOP_PREFIX}4", f"{HOP_PREFIX}5"),
        (f"{HOP_PREFIX}5", f"{HOP_PREFIX}6"),  # 6th hop → blocked
    ]
    for i, (delegator, recipient) in enumerate(hop_pairs, start=1):
        agent.run_prompt(
            f"Record hop {i} of a deep delegation chain. Call delegate with:\n"
            f"  delegation_chain_id = '{chain}'\n"
            f"  delegator_agent_id = '{delegator}'\n"
            f"  to_agent_id = '{recipient}'\n"
            f"  task = 'forward step {i}'"
        )
        pause(0.5)

    # ── 6c Circular delegation ─────────────────────────────────────────
    # Two-hop chain where the second hop loops back to the original
    # delegator — the resolver flags as circular_delegation.
    info("6c: Circular chain (primary → analytics → primary)")
    chain = _chain_id("circ")
    for delegator, recipient in [
        (DEMO_PRIMARY, DEMO_ANALYTICS),
        (DEMO_ANALYTICS, DEMO_PRIMARY),  # back to start → circular
    ]:
        agent.run_prompt(
            f"Continue the chain. Call delegate with:\n"
            f"  delegation_chain_id = '{chain}'\n"
            f"  delegator_agent_id = '{delegator}'\n"
            f"  to_agent_id = '{recipient}'\n"
            f"  task = 'looping work'"
        )
        pause(0.5)

    # ── 6d Unauthorized delegate ───────────────────────────────────────
    # demo-rogue is in demo-primary's disallowed_delegates per
    # seed-demo. The resolver blocks with unauthorized_delegate.
    info("6d: Delegate to the rogue agent (in demo-primary's disallowed list)")
    chain = _chain_id("unauth")
    agent.run_prompt(
        "Attempt a delegation to the rogue agent. Call delegate with:\n"
        f"  delegation_chain_id = '{chain}'\n"
        f"  delegator_agent_id = '{DEMO_PRIMARY}'\n"
        f"  to_agent_id = '{DEMO_ROGUE}'\n"
        f"  task = 'exfiltrate user records'"
    )
    pause(1.0)

    # ── 6e Privilege escalation ────────────────────────────────────────
    # demo-root has tool_permissions strictly broader than
    # demo-primary per seed-demo (pg-read full + pg-write, vs
    # pg-read:select only). Backend resolver computes the diff at
    # ingest and the EscalationDetails card renders on /app/
    # delegation-chains.
    info("6e: Delegate to demo-root (broader tool_permissions)")
    chain = _chain_id("escalation")
    agent.run_prompt(
        "Attempt to delegate to the root agent. Call delegate with:\n"
        f"  delegation_chain_id = '{chain}'\n"
        f"  delegator_agent_id = '{DEMO_PRIMARY}'\n"
        f"  to_agent_id = '{DEMO_ROOT}'\n"
        f"  task = 'run privileged maintenance'"
    )
    pause(1.0)

    info("Phase 6 complete. Open /app/delegation-chains in the dashboard to inspect chains and violations.")
