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
        f"WICHTIG: Du MUSST alle Aktionen selbst über Shell-Tools ausführen. "
        f"Antworte NIEMALS nur mit Text — führe die gh-Commands aktiv aus.\n"
        f"{config.additional_instructions}"
    )

    prompt = (
        f"Analysiere Issue #{issue_number} und erstelle einen Implementierungsplan.\n\n"
        f"Führe diese Schritte ALS SHELL-COMMANDS aus (nicht als Text-Antwort!):\n\n"
        f"1. `gh issue view {issue_number} --json title,body,labels`\n"
        f"2. Analysiere die Repository-Struktur mit `find . -type f | head -50` und lies relevante Dateien\n"
        f"3. `gh api repos/{config.repo_owner}/{config.repo_name}/issues/{issue_number}/reactions -f content=eyes`\n"
        f"4. Erstelle den Plan und poste ihn:\n"
        f"   `gh issue comment {issue_number} --body '<DEIN PLAN>'`\n"
        f"   Der Plan MUSS zwischen <!-- copilot:plan --> und <!-- /copilot:plan --> Markern stehen.\n"
        f"5. `gh issue edit {issue_number} --remove-label {config.trigger_label} --add-label copilot:plan`\n\n"
        f"Du bist NICHT fertig, bis du `gh issue comment` und `gh issue edit` ausgeführt hast."
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
        check = subprocess.run(
            ["gh", "issue", "view", issue_number, "--json", "comments", "-q", ".comments | length"],
            capture_output=True, text=True, timeout=10,
        )
        comment_count = check.stdout.strip() if check.returncode == 0 else "(error)"
        logger.info("Issue comment count: %s (returncode=%d)", comment_count, check.returncode)
        if check.returncode == 0 and comment_count == "0":
            logger.warning("FALLBACK: Agent returned text but didn't post comment — posting via gh CLI")
            body = f"<!-- copilot:plan -->\n{result}\n<!-- /copilot:plan -->"
            logger.info("Posting fallback comment (%d chars)...", len(body))
            post_result = subprocess.run(
                ["gh", "issue", "comment", issue_number, "--body", body],
                capture_output=True, text=True, check=False, timeout=30,
            )
            logger.info("Fallback comment post: returncode=%d stdout=%s stderr=%s",
                        post_result.returncode, post_result.stdout[:200], post_result.stderr[:200])
            label_result = subprocess.run(
                ["gh", "issue", "edit", issue_number,
                 "--remove-label", config.trigger_label,
                 "--add-label", "copilot:plan"],
                capture_output=True, text=True, check=False, timeout=30,
            )
            logger.info("Fallback label update: returncode=%d stderr=%s",
                        label_result.returncode, label_result.stderr[:200])
        else:
            logger.info("Agent already posted comment(s) — no fallback needed")
    else:
        logger.warning("Agent returned no result (None or empty)")

    logger.info("=== plan_issue.py finished ===")


if __name__ == "__main__":
    asyncio.run(main())
