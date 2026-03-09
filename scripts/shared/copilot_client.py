"""Copilot SDK client factory with permission handling and safety hooks."""

import asyncio
import logging
import os
import re
import subprocess
import sys
from contextlib import asynccontextmanager

from copilot import CopilotClient
from copilot.types import PermissionHandler

from .config import AgentConfig

logger = logging.getLogger("copilot-agent")

# Shell commands the agent is allowed to run
ALLOWED_SHELL_PREFIXES = (
    "gh ", "git ", "ls", "cat ", "find ", "tree", "head ", "tail ",
    "wc ", "grep ", "awk ", "sed ", "sort ", "uniq ", "diff ",
    "python -m pytest", "echo ", "mkdir ", "cp ", "mv ",
)

# Patterns that are always blocked
BLOCKED_PATTERNS = (
    re.compile(r"rm\s+-r"),
    re.compile(r"sudo\b"),
    re.compile(r"chmod\b"),
    re.compile(r"chown\b"),
    re.compile(r"wget\b"),
    re.compile(r"curl\b(?!.*localhost)"),
    re.compile(r">\s*/etc/"),
    re.compile(r"dd\s+if="),
)


def _is_shell_allowed(command: str) -> tuple[bool, str]:
    """Check if a shell command is allowed. Returns (allowed, reason)."""
    cmd = command.strip()

    for pattern in BLOCKED_PATTERNS:
        if pattern.search(cmd):
            return False, f"Blocked pattern detected: {pattern.pattern}"

    if any(cmd.startswith(prefix) for prefix in ALLOWED_SHELL_PREFIXES):
        return True, ""

    # Allow simple commands that don't modify system state
    if cmd in ("pwd", "whoami", "date", "env"):
        return True, ""

    return False, f"Command not in allowlist: {cmd.split()[0] if cmd else '(empty)'}"


def _make_pre_tool_hook(config: AgentConfig, phase: str):
    """Create an on_pre_tool_use hook with guardrails."""
    files_written = 0
    tool_call_count = 0

    async def on_pre_tool_use(input_data, invocation):
        nonlocal files_written, tool_call_count
        tool_call_count += 1

        tool_name = input_data.get("toolName", "")
        tool_args = input_data.get("toolArgs", {})
        logger.info("PRE_TOOL [#%d] tool=%s args_keys=%s", tool_call_count, tool_name, list(tool_args.keys()))

        # Guard: max files changed (implementation phase only)
        if phase == "implement" and tool_name == "write_file":
            files_written += 1
            if files_written > config.max_files_changed:
                return {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Maximum number of changed files ({config.max_files_changed}) reached. "
                        "Please reduce the scope of changes."
                    ),
                }

        # Guard: shell command allowlist
        if tool_name in ("shell", "bash"):
            command = tool_args.get("command", tool_args.get("input", ""))
            logger.info("PRE_TOOL shell command: %s", command[:200])
            allowed, reason = _is_shell_allowed(command)
            if not allowed:
                logger.warning("BLOCKED shell command: %s — %s", command, reason)
                return {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            logger.info("ALLOWED shell command")

        return {"permissionDecision": "allow"}

    return on_pre_tool_use


def _make_post_tool_hook():
    """Create an on_post_tool_use hook for audit logging."""

    async def on_post_tool_use(input_data, invocation):
        tool_name = input_data.get("toolName", "")
        tool_args = input_data.get("toolArgs", {})
        # Log full input keys for debugging hook structure
        logger.info("POST_TOOL input_keys=%s", list(input_data.keys()))

        if tool_name in ("shell", "bash"):
            cmd = tool_args.get("command", tool_args.get("input", ""))
            logger.info("AUDIT [%s]: %s", tool_name, cmd[:500])
            # Log tool output if available
            result = input_data.get("toolResult", input_data.get("result", ""))
            if result:
                result_str = str(result)[:500]
                logger.info("AUDIT [%s] output: %s", tool_name, result_str)
        elif tool_name in ("write_file", "read_file"):
            logger.info("AUDIT [%s]: %s", tool_name, tool_args.get("path", ""))
        else:
            logger.info("AUDIT [%s] args=%s", tool_name, {k: str(v)[:100] for k, v in tool_args.items()})

        return {}

    return on_post_tool_use


@asynccontextmanager
async def create_session(
    config: AgentConfig,
    skill_dir: str,
    system_message: str,
    phase: str = "plan",
):
    """Create a Copilot SDK session with safety hooks.

    Usage:
        async with create_session(config, "./skills/issue-planner", "...", "plan") as session:
            response = await session.send_and_wait({"prompt": "..."})
    """
    logger.info("Creating CopilotClient (use_logged_in_user=False)...")
    client = CopilotClient({
        "github_token": config.copilot_pat,
        "use_logged_in_user": False,
    })
    session = None
    try:
        logger.info("Starting Copilot client...")
        await client.start()
        logger.info("Copilot client started successfully")

        def _on_permission_request(request, invocation):
            logger.info("PERMISSION_REQUEST: kind=%s, tool=%s, invocation=%s",
                        request.get("kind", "?"), request.get("toolCallId", "?"),
                        invocation)
            return {"kind": "approved"}

        logger.info("Creating session: model=%s, skill_dir=%s, phase=%s", config.model, skill_dir, phase)
        logger.info("System message (first 300 chars): %s", system_message[:300])
        session_config = {
            "model": config.model,
            "skill_directories": [skill_dir],
            "system_message": {"content": system_message},
            "on_permission_request": _on_permission_request,
            "hooks": {
                "on_pre_tool_use": _make_pre_tool_hook(config, phase),
                "on_post_tool_use": _make_post_tool_hook(),
            },
        }
        if config.reasoning_effort:
            session_config["reasoning_effort"] = config.reasoning_effort
            logger.info("reasoning_effort=%s", config.reasoning_effort)
        session = await client.create_session(session_config)
        logger.info("Session created successfully")

        yield session
    finally:
        if session:
            logger.info("Destroying session...")
            await session.destroy()
            logger.info("Session destroyed")
        logger.info("Stopping Copilot client...")
        await client.stop()
        logger.info("Copilot client stopped")


async def run_agent(
    config: AgentConfig,
    skill_dir: str,
    system_message: str,
    prompt: str,
    phase: str = "plan",
) -> str | None:
    """Run an agent session with timeout and error handling.

    Returns the agent's response content, or None on failure.
    On timeout/error, posts a failure comment to the issue via gh CLI.
    """
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    logger.info("run_agent starting: phase=%s, issue=%s, timeout=%dm", phase, issue_number, config.timeout_minutes)
    logger.info("Prompt (first 300 chars): %s", prompt[:300])

    try:
        async with create_session(config, skill_dir, system_message, phase) as session:
            logger.info("Sending prompt to agent via send_and_wait (timeout=%ds)...", config.timeout_minutes * 60)
            response = await asyncio.wait_for(
                session.send_and_wait({"prompt": prompt}),
                timeout=config.timeout_minutes * 60,
            )
            if response:
                content = response.data.content
                logger.info("Agent response received: %d chars", len(content) if content else 0)
                logger.info("Response preview (first 500 chars): %s", (content or "")[:500])
                return content
            else:
                logger.warning("Agent returned None/empty response")
                return None

    except asyncio.TimeoutError:
        logger.error("Agent timed out after %d minutes", config.timeout_minutes)
        _post_failure(issue_number, f"⏱️ Agent-Timeout nach {config.timeout_minutes} Minuten.")
        return None

    except Exception:
        logger.exception("Agent session failed")
        _post_failure(issue_number, "❌ Agent-Fehler aufgetreten. Siehe Workflow-Logs für Details.")
        return None


def _post_failure(issue_number: str, message: str) -> None:
    """Post a failure comment and set copilot:failed label via gh CLI (fallback)."""
    if not issue_number:
        return
    try:
        subprocess.run(
            ["gh", "issue", "comment", issue_number, "--body", message],
            check=False, capture_output=True, timeout=30,
        )
        subprocess.run(
            ["gh", "issue", "edit", issue_number,
             "--add-label", "copilot:failed",
             "--remove-label", "copilot:plan,copilot:working"],
            check=False, capture_output=True, timeout=30,
        )
    except Exception:
        logger.exception("Failed to post failure comment")
