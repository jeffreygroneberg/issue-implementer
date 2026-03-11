"""Plan Job: Analyze an issue and post an implementation plan."""

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
    logger.info("=== plan_issue.py starting ===")
    config = load_config()
    issue_number = os.environ["ISSUE_NUMBER"]
    if not issue_number.isdigit():
        logger.error("Invalid ISSUE_NUMBER: %s", issue_number)
        sys.exit(1)
    logger.info("Issue number: %s", issue_number)

    system_message = (
        f"You are working in the repository {config.repo_owner}/{config.repo_name} "
        f"on the GitHub instance {config.github_server_url}.\n"
        f"You have access to a bash shell tool. You MUST perform all actions "
        f"through this shell tool. Before responding, think "
        f"step by step and plan your approach.\n"
        f"IMPORTANT: NEVER respond with text only — actively execute the commands.\n"
        f"If a command fails, analyze the error and try again.\n\n"
        f"{build_shell_policy()}\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Analyze Issue #{issue_number} and create an implementation plan.\n\n"
        f"Think first:\n"
        f"- What is the goal of the issue?\n"
        f"- Which files are affected?\n"
        f"- What steps are needed?\n\n"
        f"Then execute these steps as shell commands:\n\n"
        f"Step 1: Read the issue\n"
        f"```bash\ngh issue view {issue_number} --json title,body,labels\n```\n\n"
        f"Step 2: Understand the codebase\n"
        f"```bash\nfind . -type f | head -50\n```\n"
        f"Read relevant files with `cat`.\n\n"
        f"Step 3: React to the issue\n"
        f"```bash\ngh api repos/{config.repo_owner}/{config.repo_name}/issues/{issue_number}/reactions -f content=eyes\n```\n\n"
        f"Step 4: Create and post the plan\n"
        f"Create a detailed plan. ALWAYS include the following section at the end of the plan:\n"
        f"---\n"
        f"**🤖 Next steps:**\n"
        f"- 💬 Comment with feedback → the plan will be updated\n"
        f"- ✅ `/implement` → Start implementation\n"
        f"- 🚫 `/cancel` → Cancel agent\n\n"
        f"Then post the plan with:\n"
        f"```bash\ngh issue comment {issue_number} --body '<!-- copilot:plan -->\n<YOUR PLAN>\n<!-- /copilot:plan -->'\n```\n\n"
        f"Step 5: Update the labels\n"
        f"```bash\ngh issue edit {issue_number} --remove-label {config.trigger_label} --add-label copilot:plan\n```\n\n"
        f"IMPORTANT: You are NOT done until you have actually executed BOTH commands `gh issue comment` and `gh issue edit` "
        f"through the shell tool. Do NOT give a text response instead."
    )

    agent_root = os.environ.get("AGENT_ROOT", os.path.join(_SCRIPT_DIR, ".."))
    skill_dir = os.path.join(agent_root, "skills", "issue-planner")
    logger.info("Skill directory: %s (exists=%s)", skill_dir, os.path.isdir(skill_dir))
    logger.info("Sending prompt to agent...")
    result = await run_agent(config, skill_dir, system_message, prompt, phase="plan")
    logger.info("Agent returned: result_type=%s, result_len=%d", type(result).__name__, len(result) if result else 0)

    if not result:
        logger.error("Agent returned no result — failing the job")
        sys.exit(1)

    logger.info("=== plan_issue.py finished ===")


if __name__ == "__main__":
    asyncio.run(main())
