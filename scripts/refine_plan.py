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


logger = logging.getLogger("copilot-agent")


async def main() -> None:
    logger.info("=== refine_plan.py starting ===")
    config = load_config()
    issue_number = os.environ["ISSUE_NUMBER"]
    comment_body = os.environ.get("COMMENT_BODY", "")
    logger.info("Issue: %s, Comment length: %d chars", issue_number, len(comment_body))

    system_message = (
        f"Du arbeitest im Repository {config.repo_owner}/{config.repo_name} "
        f"auf der GitHub-Instanz {config.github_server_url}.\n"
        f"Du hast Zugriff auf ein bash-Shell-Tool. Du MUSST alle Aktionen "
        f"über dieses Shell-Tool ausführen. Denke Schritt für Schritt nach.\n"
        f"Wenn ein Befehl fehlschlägt, analysiere den Fehler und versuche es erneut.\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Issue #{issue_number} hat einen bestehenden Implementierungsplan. "
        f"Der User hat neues Feedback gegeben:\n\n"
        f"---\n{comment_body}\n---\n\n"
        f"Denke zuerst nach: Was genau will der User ändern? Was muss am Plan angepasst werden?\n\n"
        f"Dann führe aus:\n"
        f"1. `gh issue view {issue_number} --comments` — lies die bisherige Konversation\n"
        f"2. Identifiziere den letzten Plan (zwischen `<!-- copilot:plan -->` Markern)\n"
        f"3. Berücksichtige das Feedback und aktualisiere den Plan\n"
        f"4. Poste den aktualisierten Plan via "
        f"`gh issue comment {issue_number} --body '...'`\n"
        f"Behalte das gleiche Format bei (mit <!-- copilot:plan --> Markern).\n\n"
        f"Du bist NICHT fertig bis du `gh issue comment` ausgeführt hast."
    )

    agent_root = os.environ.get("AGENT_ROOT", os.path.join(_SCRIPT_DIR, ".."))
    skill_dir = os.path.join(agent_root, "skills", "issue-planner")
    logger.info("Skill directory: %s (exists=%s)", skill_dir, os.path.isdir(skill_dir))
    result = await run_agent(config, skill_dir, system_message, prompt, phase="plan")
    logger.info("Agent returned: result_len=%d", len(result) if result else 0)
    logger.info("=== refine_plan.py finished ===")


if __name__ == "__main__":
    asyncio.run(main())
