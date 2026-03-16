"""MITRITY MCP Gateway Governance Demo — Scenario Runner.

Drives a Claude-powered agent through five phases of governance testing,
with the Mitrity Gateway intercepting every tool call.
"""

import json
import os
import subprocess
import sys
import time

import anthropic
from rich.console import Console

from output import console, phase_header, tool_allowed, tool_blocked, tool_held, agent_message, info, print_summary, pause
from phases import phase1_normal, phase2_policy, phase3_injection, phase4_dlp, phase5_hold

# ---------------------------------------------------------------------------
# MCP Client — minimal stdio JSON-RPC 2.0 bridge to the Mitrity Gateway
# ---------------------------------------------------------------------------


class MCPClient:
    """Manages the gateway subprocess and MCP protocol communication."""

    def __init__(self, command: str, args: list[str]):
        self.process = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._request_id = 0
        self.tools: list[dict] = []

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, method: str, params: dict | None = None) -> dict | None:
        """Send a JSON-RPC request and read the response."""
        msg = {"jsonrpc": "2.0", "method": method, "id": self._next_id()}
        if params is not None:
            msg["params"] = params

        line = json.dumps(msg)
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

        # Read lines until we get a JSON-RPC response.
        # The gateway writes log lines to stdout alongside protocol messages.
        while True:
            resp_line = self.process.stdout.readline()
            if not resp_line:
                return None
            resp_line = resp_line.strip()
            if not resp_line:
                continue
            if resp_line.startswith("{"):
                return json.loads(resp_line)
            # Skip non-JSON lines (gateway log output).

    def _notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        line = json.dumps(msg)
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def initialize(self) -> None:
        """Perform the MCP initialize handshake."""
        resp = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mitrity-demo", "version": "1.0.0"},
        })
        if resp and "result" in resp:
            server_info = resp["result"].get("serverInfo", {})
            info(f"Connected to MCP server: {server_info.get('name', 'unknown')}")
        self._notify("notifications/initialized")

    def list_tools(self) -> list[dict]:
        """Discover available tools from the gateway."""
        resp = self._send("tools/list")
        if resp and "result" in resp:
            self.tools = resp["result"].get("tools", [])
        return self.tools

    def call_tool(self, name: str, arguments: dict) -> tuple[str, bool, int]:
        """Call a tool and return (result_text, was_allowed, duration_ms).

        If the gateway blocks the call, it returns an error response.
        We detect this and return was_allowed=False.
        """
        start = time.monotonic()
        resp = self._send("tools/call", {"name": name, "arguments": arguments})
        duration_ms = int((time.monotonic() - start) * 1000)

        if resp is None:
            return "No response from gateway", False, duration_ms

        if "error" in resp:
            error = resp["error"]
            message = error.get("message", "Unknown error") if isinstance(error, dict) else str(error)
            return message, False, duration_ms

        result = resp.get("result", {})
        content = result.get("content", [])
        text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(text_parts), True, duration_ms

    def close(self) -> None:
        """Shut down the gateway subprocess."""
        if self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait(timeout=5)


# ---------------------------------------------------------------------------
# Claude Agent — sends prompts and bridges tool calls via MCP
# ---------------------------------------------------------------------------


class DemoAgent:
    """Wraps the Anthropic API and MCP client for the demo scenario."""

    def __init__(self, mcp: MCPClient):
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.mcp = mcp
        # Anthropic API doesn't allow ":" in tool names, so we map
        # "fs:read_file" → "fs__read_file" for the API and back for MCP.
        self._name_to_api: dict[str, str] = {}
        self._name_to_mcp: dict[str, str] = {}
        for t in mcp.tools:
            api_name = t["name"].replace(":", "__")
            self._name_to_api[t["name"]] = api_name
            self._name_to_mcp[api_name] = t["name"]
        self._anthropic_tools = self._convert_tools(mcp.tools)

    def run_prompt(self, prompt: str, max_turns: int = 5) -> str:
        """Send a prompt to Claude and handle tool use loops.

        Returns the final text response from Claude.
        """
        messages = [{"role": "user", "content": prompt}]

        for _ in range(max_turns):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system="You are an AI agent with access to filesystem, shell, and API tools. "
                       "Use the tools provided to accomplish tasks. Be concise in your responses.",
                tools=self._anthropic_tools,
                messages=messages,
            )

            # Collect text and tool use blocks.
            text_parts = []
            tool_uses = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            # If no tool use, we're done.
            if response.stop_reason == "end_turn" or not tool_uses:
                final_text = "\n".join(text_parts)
                if final_text:
                    agent_message(final_text)
                return final_text

            # Process tool calls.
            assistant_content = response.content
            tool_results = []

            for tu in tool_uses:
                # Map API name back to MCP namespaced name (e.g. fs__read_file → fs:read_file).
                mcp_name = self._name_to_mcp.get(tu.name, tu.name)
                result_text, allowed, duration_ms = self.mcp.call_tool(mcp_name, tu.input)

                if allowed:
                    tool_allowed(mcp_name, result_text, duration_ms)
                else:
                    tool_blocked(mcp_name, result_text, duration_ms)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                    "is_error": not allowed,
                })

                pause(0.5)

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        return ""

    def _convert_tools(self, mcp_tools: list[dict]) -> list[dict]:
        """Convert MCP tool definitions to Anthropic API format."""
        anthropic_tools = []
        for t in mcp_tools:
            anthropic_tools.append({
                "name": self._name_to_api[t["name"]],
                "description": t.get("description", ""),
                "input_schema": t.get("inputSchema", {"type": "object"}),
            })
        return anthropic_tools


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    console.print()
    console.print(
        "[bold cyan]MITRITY MCP Gateway — Governance Demo[/bold cyan]",
        justify="center",
    )
    console.print(
        "[dim]Demonstrating real-time AI agent governance with policy enforcement[/dim]",
        justify="center",
    )
    console.print()

    # Start the Mitrity Gateway as an MCP server.
    info("Starting Mitrity Gateway...")
    mcp = MCPClient("/usr/local/bin/mitrity-gateway", ["--config", "/etc/mitrity/gateway.yaml"])

    try:
        mcp.initialize()

        # Discover tools.
        tools = mcp.list_tools()
        info(f"Discovered {len(tools)} tools: {', '.join(t['name'] for t in tools)}")
        pause(1.0)

        # Create the demo agent.
        agent = DemoAgent(mcp)

        # Run scenario phases.
        phases = [
            (1, "Normal Operations", phase1_normal.run),
            (2, "Policy Violations", phase2_policy.run),
            (3, "Prompt Injection", phase3_injection.run),
            (4, "DLP & Data Protection", phase4_dlp.run),
            (5, "Escalation & Hold", phase5_hold.run),
        ]

        for num, title, run_fn in phases:
            phase_header(num, title)
            run_fn(agent)
            pause(2.0)

        print_summary()

    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted.[/yellow]")
        print_summary()
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        raise
    finally:
        mcp.close()


if __name__ == "__main__":
    main()
