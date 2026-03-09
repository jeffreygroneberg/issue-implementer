"""Plan Job: Analyze an issue and post an implementation plan."""

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

    system_message = (
        f"Du arbeitest im Repository {config.repo_owner}/{config.repo_name} "
        f"auf der GitHub-Instanz {config.github_server_url}.\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Analysiere Issue #{issue_number} im Repository {config.repo_owner}/{config.repo_name} "
        f"und erstelle einen Implementierungsplan.\n\n"
        f"Schritte:\n"
        f"1. Lies das Issue via `gh issue view {issue_number} --json title,body,labels`\n"
        f"2. Analysiere die Repository-Struktur\n"
        f"3. Erstelle einen strukturierten Implementierungsplan\n"
        f"4. Setze eine 👀 Reaction auf das Issue via "
        f"`gh api repos/{config.repo_owner}/{config.repo_name}/issues/{issue_number}/reactions -f content=eyes`\n"
        f"5. Poste den Plan als Kommentar via `gh issue comment {issue_number} --body '...'`\n"
        f"6. Aktualisiere Labels: `gh issue edit {issue_number} "
        f"--remove-label {config.trigger_label} --add-label copilot:plan`"
    )

    agent_root = os.environ.get("AGENT_ROOT", os.path.join(_SCRIPT_DIR, ".."))
    skill_dir = os.path.join(agent_root, "skills", "issue-planner")
    await run_agent(config, skill_dir, system_message, prompt, phase="plan")


if __name__ == "__main__":
    asyncio.run(main())
