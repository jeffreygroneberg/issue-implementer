"""Implement Job: Read the approved plan, create a branch, implement code, push, and open a PR."""

import asyncio
import logging
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, ".."))

from shared.config import load_config
from shared.copilot_client import build_shell_policy, run_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


logger = logging.getLogger("copilot-agent")


async def main() -> None:
    logger.info("=== implement_issue.py starting ===")
    config = load_config()
    issue_number = os.environ["ISSUE_NUMBER"]
    if not issue_number.isdigit():
        logger.error("Invalid ISSUE_NUMBER: %s", issue_number)
        sys.exit(1)
    comment_author = os.environ.get("COMMENT_AUTHOR", "unknown")
    # Sanitize author to alphanumeric, hyphens, underscores (valid GitHub usernames)
    if not re.match(r'^[a-zA-Z0-9_-]+$', comment_author):
        logger.error("Invalid COMMENT_AUTHOR: %s", comment_author)
        sys.exit(1)
    logger.info("Issue: %s, Author: %s", issue_number, comment_author)

    system_message = (
        f"You are working in the repository {config.repo_owner}/{config.repo_name} "
        f"on the GitHub instance {config.github_server_url}.\n"
        f"The default branch is '{config.default_branch}'.\n"
        f"The user '{comment_author}' has requested the implementation.\n"
        f"You have access to a bash shell tool. You MUST perform all actions "
        f"through this shell tool. Think step by step.\n"
        f"If a command fails, analyze the error and try again.\n\n"
        f"{build_shell_policy()}\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Implement Issue #{issue_number} in the repository {config.repo_owner}/{config.repo_name}.\n\n"
        f"Think first: What exactly needs to be implemented? Which files need to be changed?\n\n"
        f"Steps:\n"
        f"1. Read the comments via `gh issue view {issue_number} --comments` and extract "
        f"the latest plan (between `<!-- copilot:plan -->` and `<!-- /copilot:plan -->` markers)\n"
        f"2. Update labels: `gh issue edit {issue_number} "
        f"--remove-label copilot:plan --add-label copilot:working`\n"
        f"3. Create branch: `git checkout -b copilot/issue-{issue_number}`\n"
        f"4. Implement the code according to the plan\n"
        f"5. Commit: `git add .` then `git commit -m 'feat: ...' "
        f"--trailer 'Co-authored-by: {comment_author}'`\n"
        f"6. Push: `git push origin copilot/issue-{issue_number}`\n"
        f"7. Create draft PR: `gh pr create --draft "
        f"--title '[Copilot] <issue-title>' "
        f"--body '...' --base {config.default_branch}`\n"
        f"8. Comment on the issue with the PR link\n"
        f"9. Update labels: `gh issue edit {issue_number} "
        f"--remove-label copilot:working --add-label copilot:review`"
    )

    agent_root = os.environ.get("AGENT_ROOT", os.path.join(_SCRIPT_DIR, ".."))
    skill_dir = os.path.join(agent_root, "skills", "issue-implementer")
    logger.info("Skill directory: %s (exists=%s)", skill_dir, os.path.isdir(skill_dir))
    result = await run_agent(config, skill_dir, system_message, prompt, phase="implement")
    logger.info("Agent returned: result_len=%d", len(result) if result else 0)
    logger.info("=== implement_issue.py finished ===")


if __name__ == "__main__":
    asyncio.run(main())
