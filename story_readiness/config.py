"""Environment-driven configuration for the Story Readiness analyzer."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv


@dataclass
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    projects: List[str]
    label: str
    ac_field: str


@dataclass
class LLMConfig:
    provider: str
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    azure_endpoint: str = ""
    azure_api_key: str = ""
    azure_deployment: str = ""
    azure_api_version: str = "2024-10-21"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    gh_models_token: str = ""
    gh_models_endpoint: str = "https://models.github.ai/inference"
    gh_models_model: str = "openai/gpt-4o-mini"


@dataclass
class RuntimeConfig:
    output_dir: Path
    max_issues: int = 0
    exclude_keys: List[str] = field(default_factory=list)
    include_keys: List[str] = field(default_factory=list)
    post_comments: bool = False


@dataclass
class AppConfig:
    jira: JiraConfig
    llm: LLMConfig
    runtime: RuntimeConfig


def _csv(value: str) -> List[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _required(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return val


def validate_jira_base_url(url: str) -> None:
    """Refuse sandbox URLs unless ALLOW_SANDBOX=1 is explicitly set.

    The tool is intended to operate against the Ashley Furniture production
    Jira tenant. Accidentally pointing it at ``*-sandbox.atlassian.net`` would
    post grooming comments on stale ticket copies that nobody sees.
    """
    if "sandbox" in url.lower() and os.getenv("ALLOW_SANDBOX", "").strip() not in (
        "1",
        "true",
        "True",
    ):
        raise RuntimeError(
            f"Refusing to use Jira base URL '{url}' - it looks like a sandbox "
            "tenant. This tool targets production. If you really need sandbox, "
            "set ALLOW_SANDBOX=1 explicitly."
        )


def load_config(env_file: str | None = None) -> AppConfig:
    """Load configuration from the environment (and optional .env file)."""
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)

    jira = JiraConfig(
        base_url=_required("JIRA_BASE_URL").rstrip("/"),
        email=_required("JIRA_EMAIL"),
        api_token=_required("JIRA_API_TOKEN"),
        projects=_csv(os.getenv("JIRA_PROJECTS", "WW,WR")),
        label=os.getenv("JIRA_LABEL", "Estimate"),
        ac_field=os.getenv("JIRA_AC_FIELD", "customfield_10091").strip(),
    )
    validate_jira_base_url(jira.base_url)

    provider = os.getenv("LLM_PROVIDER", "github_models").strip().lower()
    # GitHub Actions exposes its built-in token as GITHUB_TOKEN; accept that too.
    gh_token = (
        os.getenv("GH_MODELS_TOKEN")
        or os.getenv("GITHUB_TOKEN")
        or ""
    )
    llm = LLMConfig(
        provider=provider,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/"),
        azure_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
        azure_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
        gh_models_token=gh_token,
        gh_models_endpoint=os.getenv(
            "GH_MODELS_ENDPOINT", "https://models.github.ai/inference"
        ).rstrip("/"),
        gh_models_model=os.getenv("GH_MODELS_MODEL", "openai/gpt-4o-mini"),
    )
    _validate_llm(llm)

    runtime = RuntimeConfig(
        output_dir=Path(os.getenv("OUTPUT_DIR", "./output")).resolve(),
        max_issues=int(os.getenv("MAX_ISSUES", "0") or "0"),
        exclude_keys=_csv(os.getenv("EXCLUDE_KEYS", "")),
        include_keys=_csv(os.getenv("INCLUDE_KEYS", "")),
        post_comments=os.getenv("POST_COMMENTS", "0").strip() in ("1", "true", "True"),
    )
    runtime.output_dir.mkdir(parents=True, exist_ok=True)

    return AppConfig(jira=jira, llm=llm, runtime=runtime)


def _validate_llm(cfg: LLMConfig) -> None:
    if cfg.provider == "openai":
        if not cfg.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
    elif cfg.provider == "azure":
        missing = [
            name
            for name, val in (
                ("AZURE_OPENAI_ENDPOINT", cfg.azure_endpoint),
                ("AZURE_OPENAI_API_KEY", cfg.azure_api_key),
                ("AZURE_OPENAI_DEPLOYMENT", cfg.azure_deployment),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                "Azure OpenAI configuration incomplete: missing " + ", ".join(missing)
            )
    elif cfg.provider == "anthropic":
        if not cfg.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )
    elif cfg.provider == "github_models":
        if not cfg.gh_models_token:
            raise RuntimeError(
                "GH_MODELS_TOKEN (or GITHUB_TOKEN in Actions) is required "
                "when LLM_PROVIDER=github_models"
            )
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{cfg.provider}'. "
            "Use openai, azure, anthropic, or github_models."
        )
