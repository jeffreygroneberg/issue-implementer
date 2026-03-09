"""Load agent configuration from .github/copilot-agent.yml with sensible defaults."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


_DEFAULTS = {
    "trigger_label": "copilot",
    "implement_command": "/implement",
    "cancel_command": "/cancel",
    "model": "gpt-4.1",
    "max_refinement_rounds": 10,
    "max_files_changed": 10,
    "timeout_minutes": 15,
    "additional_instructions": "",
}


@dataclass
class AgentConfig:
    trigger_label: str = _DEFAULTS["trigger_label"]
    implement_command: str = _DEFAULTS["implement_command"]
    cancel_command: str = _DEFAULTS["cancel_command"]
    model: str = _DEFAULTS["model"]
    max_refinement_rounds: int = _DEFAULTS["max_refinement_rounds"]
    max_files_changed: int = _DEFAULTS["max_files_changed"]
    timeout_minutes: int = _DEFAULTS["timeout_minutes"]
    additional_instructions: str = _DEFAULTS["additional_instructions"]

    # From environment
    github_token: str = field(default="", repr=False)
    copilot_pat: str = field(default="", repr=False)
    repo_owner: str = ""
    repo_name: str = ""
    github_server_url: str = ""
    gh_host: str = ""
    default_branch: str = "main"


def load_config() -> AgentConfig:
    """Load config from YAML file + environment variables."""
    config_path = Path(".github/copilot-agent.yml")
    file_values: dict = {}
    if config_path.exists():
        with open(config_path) as f:
            file_values = yaml.safe_load(f) or {}

    cfg = AgentConfig(
        trigger_label=file_values.get("trigger_label", _DEFAULTS["trigger_label"]),
        implement_command=file_values.get("implement_command", _DEFAULTS["implement_command"]),
        cancel_command=file_values.get("cancel_command", _DEFAULTS["cancel_command"]),
        model=file_values.get("model", _DEFAULTS["model"]),
        max_refinement_rounds=int(file_values.get("max_refinement_rounds", _DEFAULTS["max_refinement_rounds"])),
        max_files_changed=int(file_values.get("max_files_changed", _DEFAULTS["max_files_changed"])),
        timeout_minutes=int(file_values.get("timeout_minutes", _DEFAULTS["timeout_minutes"])),
        additional_instructions=file_values.get("additional_instructions", _DEFAULTS["additional_instructions"]),
    )

    # Environment overrides (from composite action inputs)
    cfg.model = os.environ.get("MODEL", cfg.model)
    cfg.max_files_changed = int(os.environ.get("MAX_FILES_CHANGED", cfg.max_files_changed))
    cfg.timeout_minutes = int(os.environ.get("TIMEOUT_MINUTES", cfg.timeout_minutes))

    # Environment variables
    cfg.github_token = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
    cfg.copilot_pat = os.environ.get("COPILOT_PAT", "")
    cfg.github_server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    cfg.gh_host = os.environ.get("GH_HOST", "")
    cfg.default_branch = os.environ.get("DEFAULT_BRANCH", "main")

    repo_full = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo_full:
        cfg.repo_owner, cfg.repo_name = repo_full.split("/", 1)

    return cfg
