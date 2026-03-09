"""Implement Job: Read the approved plan, create a branch, implement code, push, and open a PR."""

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
    logger.info("=== implement_issue.py starting ===")
    config = load_config()
    issue_number = os.environ["ISSUE_NUMBER"]
    comment_author = os.environ.get("COMMENT_AUTHOR", "unknown")
    logger.info("Issue: %s, Author: %s", issue_number, comment_author)

    system_message = (
        f"Du arbeitest im Repository {config.repo_owner}/{config.repo_name} "
        f"auf der GitHub-Instanz {config.github_server_url}.\n"
        f"Der Default-Branch ist '{config.default_branch}'.\n"
        f"Der User '{comment_author}' hat die Implementierung angefordert.\n"
        f"Du hast Zugriff auf ein bash-Shell-Tool. Du MUSST alle Aktionen "
        f"über dieses Shell-Tool ausführen. Denke Schritt für Schritt nach.\n"
        f"Wenn ein Befehl fehlschlägt, analysiere den Fehler und versuche es erneut.\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Implementiere Issue #{issue_number} im Repository {config.repo_owner}/{config.repo_name}.\n\n"
        f"Denke zuerst nach: Was genau soll implementiert werden? Welche Dateien müssen geändert werden?\n\n"
        f"Schritte:\n"
        f"1. Lies die Kommentare via `gh issue view {issue_number} --comments` und extrahiere "
        f"den letzten Plan (zwischen `<!-- copilot:plan -->` und `<!-- /copilot:plan -->` Markern)\n"
        f"2. Aktualisiere Labels: `gh issue edit {issue_number} "
        f"--remove-label copilot:plan --add-label copilot:working`\n"
        f"3. Erstelle Branch: `git checkout -b copilot/issue-{issue_number}`\n"
        f"4. Implementiere den Code gemäß Plan\n"
        f"5. Committe: `git add .` dann `git commit -m 'feat: ...' "
        f"--trailer 'Co-authored-by: {comment_author}'`\n"
        f"6. Pushe: `git push origin copilot/issue-{issue_number}`\n"
        f"7. Erstelle Draft-PR: `gh pr create --draft "
        f"--title '[Copilot] <issue-titel>' "
        f"--body '...' --base {config.default_branch}`\n"
        f"8. Kommentiere das Issue mit dem PR-Link\n"
        f"9. Aktualisiere Labels: `gh issue edit {issue_number} "
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
