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
    config = load_config()
    issue_number = os.environ["ISSUE_NUMBER"]

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
    result = await run_agent(config, skill_dir, system_message, prompt, phase="plan")

    # Fallback: if the agent returned text but didn't post a comment, post it ourselves
    if result:
        check = subprocess.run(
            ["gh", "issue", "view", issue_number, "--json", "comments", "-q", ".comments | length"],
            capture_output=True, text=True, timeout=10,
        )
        if check.returncode == 0 and check.stdout.strip() == "0":
            logger.warning("Agent returned text but didn't post comment — posting fallback")
            body = f"<!-- copilot:plan -->\n{result}\n<!-- /copilot:plan -->"
            subprocess.run(
                ["gh", "issue", "comment", issue_number, "--body", body],
                check=False, timeout=30,
            )
            subprocess.run(
                ["gh", "issue", "edit", issue_number,
                 "--remove-label", config.trigger_label,
                 "--add-label", "copilot:plan"],
                check=False, timeout=30,
            )


if __name__ == "__main__":
    asyncio.run(main())
