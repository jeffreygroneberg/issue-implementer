"""Plan Job: Analyze an issue and post an implementation plan."""

import asyncio
import logging
import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, ".."))

from shared.config import load_config
from shared.copilot_client import run_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("copilot-agent")


async def main() -> None:
    logger.info("=== plan_issue.py starting ===")
    config = load_config()
    issue_number = os.environ["ISSUE_NUMBER"]
    logger.info("Issue number: %s", issue_number)

    system_message = (
        f"Du arbeitest im Repository {config.repo_owner}/{config.repo_name} "
        f"auf der GitHub-Instanz {config.github_server_url}.\n"
        f"Du hast Zugriff auf ein bash-Shell-Tool. Du MUSST alle Aktionen "
        f"über dieses Shell-Tool ausführen. Bevor du antwortest, denke "
        f"Schritt für Schritt nach und plane dein Vorgehen.\n"
        f"WICHTIG: Antworte NIEMALS nur mit Text — führe die Befehle aktiv aus.\n"
        f"Wenn ein Befehl fehlschlägt, analysiere den Fehler und versuche es erneut.\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Analysiere Issue #{issue_number} und erstelle einen Implementierungsplan.\n\n"
        f"Denke zuerst nach:\n"
        f"- Was ist das Ziel des Issues?\n"
        f"- Welche Dateien sind betroffen?\n"
        f"- Welche Schritte sind nötig?\n\n"
        f"Dann führe diese Schritte als Shell-Commands aus:\n\n"
        f"Schritt 1: Lies das Issue\n"
        f"```bash\ngh issue view {issue_number} --json title,body,labels\n```\n\n"
        f"Schritt 2: Verstehe die Codebase\n"
        f"```bash\nfind . -type f | head -50\n```\n"
        f"Lies relevante Dateien mit `cat`.\n\n"
        f"Schritt 3: Reagiere auf das Issue\n"
        f"```bash\ngh api repos/{config.repo_owner}/{config.repo_name}/issues/{issue_number}/reactions -f content=eyes\n```\n\n"
        f"Schritt 4: Erstelle und poste den Plan\n"
        f"Erstelle einen detaillierten Plan. Poste ihn dann mit:\n"
        f"```bash\ngh issue comment {issue_number} --body '<!-- copilot:plan -->\n<DEIN PLAN>\n<!-- /copilot:plan -->'\n```\n\n"
        f"Schritt 5: Aktualisiere die Labels\n"
        f"```bash\ngh issue edit {issue_number} --remove-label {config.trigger_label} --add-label copilot:plan\n```\n\n"
        f"WICHTIG: Du bist NICHT fertig, bis du BEIDE Befehle `gh issue comment` und `gh issue edit` "
        f"tatsächlich über das Shell-Tool ausgeführt hast. Gib KEINE Text-Antwort stattdessen."
    )

    agent_root = os.environ.get("AGENT_ROOT", os.path.join(_SCRIPT_DIR, ".."))
    skill_dir = os.path.join(agent_root, "skills", "issue-planner")
    logger.info("Skill directory: %s (exists=%s)", skill_dir, os.path.isdir(skill_dir))
    logger.info("Sending prompt to agent...")
    result = await run_agent(config, skill_dir, system_message, prompt, phase="plan")
    logger.info("Agent returned: result_type=%s, result_len=%d", type(result).__name__, len(result) if result else 0)

    # Fallback: if the agent returned text but didn't post a comment, post it ourselves
    if result:
        logger.info("Checking if agent posted a comment on the issue...")
        repo = f"{config.repo_owner}/{config.repo_name}"
        check = subprocess.run(
            ["gh", "issue", "view", issue_number, "--repo", repo,
             "--json", "comments", "-q", ".comments | length"],
            capture_output=True, text=True, timeout=10,
        )
        logger.info("Comment check: returncode=%d stdout=%r stderr=%r",
                    check.returncode, check.stdout.strip(), check.stderr.strip()[:200])

        needs_fallback = False
        if check.returncode != 0:
            logger.warning("gh issue view failed (rc=%d) — assuming no comments, will fallback", check.returncode)
            needs_fallback = True
        elif check.stdout.strip() == "0":
            logger.info("Confirmed: 0 comments on issue")
            needs_fallback = True
        else:
            logger.info("Agent already posted %s comment(s) — no fallback needed", check.stdout.strip())

        if needs_fallback:
            logger.warning("FALLBACK: Posting agent result as comment via gh CLI")
            body = f"<!-- copilot:plan -->\n{result}\n<!-- /copilot:plan -->"
            logger.info("Posting fallback comment (%d chars)...", len(body))
            post_result = subprocess.run(
                ["gh", "issue", "comment", issue_number, "--repo", repo, "--body", body],
                capture_output=True, text=True, check=False, timeout=30,
            )
            logger.info("Fallback comment post: returncode=%d stdout=%s stderr=%s",
                        post_result.returncode, post_result.stdout[:200], post_result.stderr[:200])
            label_result = subprocess.run(
                ["gh", "issue", "edit", issue_number, "--repo", repo,
                 "--remove-label", config.trigger_label,
                 "--add-label", "copilot:plan"],
                capture_output=True, text=True, check=False, timeout=30,
            )
            logger.info("Fallback label update: returncode=%d stderr=%s",
                        label_result.returncode, label_result.stderr[:200])
    else:
        logger.warning("Agent returned no result (None or empty)")

    logger.info("=== plan_issue.py finished ===")


if __name__ == "__main__":
    asyncio.run(main())
