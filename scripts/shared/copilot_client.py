"""Copilot SDK client factory with permission handling and safety hooks."""

import asyncio
import logging
import os
import re
import subprocess
import sys
from contextlib import asynccontextmanager

from copilot import CopilotClient

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

    async def on_pre_tool_use(input_data, invocation):
        nonlocal files_written

        tool_name = input_data.get("toolName", "")
        tool_args = input_data.get("toolArgs", {})

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
        if tool_name == "shell":
            command = tool_args.get("command", "")
            allowed, reason = _is_shell_allowed(command)
            if not allowed:
                logger.warning("Blocked shell command: %s — %s", command, reason)
                return {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }

        return {"permissionDecision": "allow"}

    return on_pre_tool_use


def _make_post_tool_hook():
    """Create an on_post_tool_use hook for audit logging."""

    async def on_post_tool_use(input_data, invocation):
        tool_name = input_data.get("toolName", "")
        tool_args = input_data.get("toolArgs", {})

        if tool_name == "shell":
            logger.info("AUDIT [shell]: %s", tool_args.get("command", ""))
        elif tool_name in ("write_file", "read_file"):
            logger.info("AUDIT [%s]: %s", tool_name, tool_args.get("path", ""))
        else:
            logger.info("AUDIT [%s]", tool_name)

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
    client = CopilotClient({
        "github_token": config.copilot_pat,
        "use_logged_in_user": False,
    })
    session = None
    try:
        await client.start()

        session = await client.create_session({
            "model": config.model,
            "skill_directories": [skill_dir],
            "system_message": {"content": system_message},
            "on_permission_request": lambda req: {"kind": "approved"},
            "hooks": {
                "on_pre_tool_use": _make_pre_tool_hook(config, phase),
                "on_post_tool_use": _make_post_tool_hook(),
            },
        })

        yield session
    finally:
        if session:
            await session.destroy()
        await client.stop()


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

    try:
        async with create_session(config, skill_dir, system_message, phase) as session:
            response = await asyncio.wait_for(
                session.send_and_wait({"prompt": prompt}),
                timeout=config.timeout_minutes * 60,
            )
            return response.data.content if response else None

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
