"""Phase 6: Delegation Chains — multi-agent governance.

Each sub-scenario invokes the `delegate` tool one or more times. The gateway
intercepts the calls and runs them through the delegation engine. The
audience watches the result land on the dashboard at /app/delegation-chains.

Sub-scenarios:

  6a Clean delegation       — a simple two-hop chain that should be allowed.
  6b Depth exceeded         — chain of 6 hops, exceeds the default
                              max_chain_depth=5; the 6th hop blocks.
  6c Circular delegation    — same agent appears twice in the chain.
  6d Unauthorized delegate  — REQUIRES BACKEND CONFIG: the delegate's
                              agent ID must be in the demo agent's
                              `disallowed_delegates` list. Without that
                              configuration the call appears as allowed.
  6e Privilege escalation   — REQUIRES BACKEND CONFIG: the delegate must
                              be a registered agent with tool_permissions
                              broader than the demo agent's. Without
                              that configuration the engine's lookup
                              returns nil and the check silently skips.

Sub-scenarios 6a–6c work against the default delegation settings the
backend ships with every tenant. 6d/6e require explicit per-agent
configuration (planned as part of the demo-tenant seed work).
"""

import time

from output import info, pause


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
        f"  delegator_agent_id = 'demo-agent'\n"
        f"  delegator_agent_name = 'Demo Agent'\n"
        f"  delegator_mission_scope = 'workspace operations'\n"
        f"  to_agent_id = 'demo-analytics'\n"
        f"  to_agent_name = 'Analytics Agent'\n"
        f"  task = 'Compute today\\'s order total'"
    )
    pause(2.0)

    # ── 6b Depth exceeded ──────────────────────────────────────────────
    # Six hops on the same chain_id. The 6th exceeds the default
    # max_chain_depth=5 and the backend's hop-violation resolver flags
    # it as depth_exceeded. Each call sets a different delegator so the
    # backend sees a real multi-hop chain (no in-process multi-agent
    # orchestration needed).
    info("6b: Chain of 6 hops exceeding the default depth limit (=5)")
    chain = _chain_id("deep")
    hop_pairs = [
        ("demo-agent", "demo-h1"),
        ("demo-h1", "demo-h2"),
        ("demo-h2", "demo-h3"),
        ("demo-h3", "demo-h4"),
        ("demo-h4", "demo-h5"),
        ("demo-h5", "demo-h6"),  # 6th hop → blocked
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
    # Three-hop chain where the third hop loops back to an agent
    # already in the chain — the resolver flags as circular_delegation.
    info("6c: Circular chain (A→B→A)")
    chain = _chain_id("circ")
    for delegator, recipient in [
        ("demo-agent", "demo-helper"),
        ("demo-helper", "demo-agent"),  # back to start → circular
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
    # REQUIRES backend config: the demo agent must have
    # `disallowed_delegates = ['demo-rogue']` (or
    # `allowed_delegates` set without 'demo-rogue' in it). Without
    # that, the engine treats this as a clean delegation.
    info("6d: Delegate to a denied agent (requires backend config to enforce)")
    chain = _chain_id("unauth")
    agent.run_prompt(
        "Attempt a delegation to the rogue agent. Call delegate with:\n"
        f"  delegation_chain_id = '{chain}'\n"
        f"  delegator_agent_id = 'demo-agent'\n"
        f"  to_agent_id = 'demo-rogue'\n"
        f"  task = 'exfiltrate user records'"
    )
    pause(1.0)

    # ── 6e Privilege escalation ────────────────────────────────────────
    # REQUIRES backend config: `demo-root` must be registered with
    # broader tool_permissions than `demo-agent` so the engine's
    # delegator-vs-delegate diff finds escalated (tool, op) pairs.
    info("6e: Delegate to a broader-privilege agent (requires backend config)")
    chain = _chain_id("escalation")
    agent.run_prompt(
        "Attempt to delegate to the root agent. Call delegate with:\n"
        f"  delegation_chain_id = '{chain}'\n"
        f"  delegator_agent_id = 'demo-agent'\n"
        f"  to_agent_id = 'demo-root'\n"
        f"  task = 'run privileged maintenance'"
    )
    pause(1.0)

    info("Phase 6 complete. Open /app/delegation-chains in the dashboard to inspect chains and violations.")
