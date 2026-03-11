"""Refine Job: Process user feedback and post an updated plan."""

import asyncio
import logging
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, ".."))

from shared.config import load_config
from shared.copilot_client import build_shell_policy, run_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


logger = logging.getLogger("copilot-agent")


async def main() -> None:
    logger.info("=== refine_plan.py starting ===")
    config = load_config()
    issue_number = os.environ["ISSUE_NUMBER"]
    if not issue_number.isdigit():
        logger.error("Invalid ISSUE_NUMBER: %s", issue_number)
        sys.exit(1)
    comment_body = os.environ.get("COMMENT_BODY", "")
    logger.info("Issue: %s, Comment length: %d chars", issue_number, len(comment_body))

    system_message = (
        f"You are working in the repository {config.repo_owner}/{config.repo_name} "
        f"on the GitHub instance {config.github_server_url}.\n"
        f"You have access to a bash shell tool. You MUST perform all actions "
        f"through this shell tool. Think step by step.\n"
        f"If a command fails, analyze the error and try again.\n\n"
        f"{build_shell_policy()}\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Issue #{issue_number} has an existing implementation plan. "
        f"The user has provided new feedback:\n\n"
        f"---\n{comment_body}\n---\n\n"
        f"Think first: What exactly does the user want to change? What needs to be adjusted in the plan?\n\n"
        f"Then execute:\n"
        f"1. `gh issue view {issue_number} --comments` — read the existing conversation\n"
        f"2. Identify the latest plan (between `<!-- copilot:plan -->` markers)\n"
        f"3. Consider the feedback and update the plan\n"
        f"4. Post the updated plan via "
        f"`gh issue comment {issue_number} --body '...'`\n"
        f"Keep the same format (with <!-- copilot:plan --> markers).\n\n"
        f"You are NOT done until you have executed `gh issue comment`."
    )

    agent_root = os.environ.get("AGENT_ROOT", os.path.join(_SCRIPT_DIR, ".."))
    skill_dir = os.path.join(agent_root, "skills", "issue-planner")
    logger.info("Skill directory: %s (exists=%s)", skill_dir, os.path.isdir(skill_dir))
    result = await run_agent(config, skill_dir, system_message, prompt, phase="plan")
    logger.info("Agent returned: result_len=%d", len(result) if result else 0)
    logger.info("=== refine_plan.py finished ===")


if __name__ == "__main__":
    asyncio.run(main())
