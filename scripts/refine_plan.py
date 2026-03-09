"""Refine Job: Process user feedback and post an updated plan."""

import asyncio
import logging
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, ".."))

from shared.config import load_config
from shared.copilot_client import run_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main() -> None:
    config = load_config()
    issue_number = os.environ["ISSUE_NUMBER"]
    comment_body = os.environ.get("COMMENT_BODY", "")

    system_message = (
        f"Du arbeitest im Repository {config.repo_owner}/{config.repo_name} "
        f"auf der GitHub-Instanz {config.github_server_url}.\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Issue #{issue_number} hat einen bestehenden Implementierungsplan. "
        f"Der User hat neues Feedback gegeben:\n\n"
        f"---\n{comment_body}\n---\n\n"
        f"Schritte:\n"
        f"1. Lies die bisherige Konversation via `gh issue view {issue_number} --comments`\n"
        f"2. Identifiziere den letzten Plan (zwischen `<!-- copilot:plan -->` Markern)\n"
        f"3. Berücksichtige das Feedback und aktualisiere den Plan\n"
        f"4. Poste den aktualisierten Plan als neuen Kommentar via "
        f"`gh issue comment {issue_number} --body '...'`\n"
        f"Behalte das gleiche Format bei (mit <!-- copilot:plan --> Markern)."
    )

    agent_root = os.environ.get("AGENT_ROOT", os.path.join(_SCRIPT_DIR, ".."))
    skill_dir = os.path.join(agent_root, "skills", "issue-planner")
    await run_agent(config, skill_dir, system_message, prompt, phase="plan")


if __name__ == "__main__":
    asyncio.run(main())
