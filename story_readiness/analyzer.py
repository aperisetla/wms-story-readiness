"""Triage and LLM orchestration for the six-part Story Readiness framework."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List

from . import prompts
from .config import LLMConfig
from .jira_client import JiraIssue

log = logging.getLogger(__name__)


EDGE_CASE_TRIGGERS = (
    r"\b(invent(ory|ories)|pick|pack|putaway|receiv(e|ing)|lot|serial|batch|"
    r"short|backorder|hold|transfer|return|exception|cycle\s*count|wave|lpn|"
    r"scanner|override)\b"
)
INTEGRATION_TRIGGERS = (
    r"\b(storis|erp|tms|oms|proship|carrier|edi|api|interface|as\s*/?400|"
    r"highjump|automation|rf|scanner|asn|webhook|xml|print(er|ing)|queue)\b"
)
SLOTTING_TRIGGERS = (
    r"\b(slot(t?ing)?|replenish(ment)?|alloca(te|tion)|forward[\s-]?pick|"
    r"case\s*good|casegood|dynamic\s+slot)\b"
)


@dataclass
class ReadinessFlags:
    has_description: bool
    has_acceptance_criteria: bool
    has_user_story_format: bool
    flags: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        return "\n".join(f"- {f}" for f in self.flags) or "- (none detected)"


def compute_readiness_flags(issue: JiraIssue) -> ReadinessFlags:
    desc = issue.description or ""
    ac = issue.acceptance_criteria or ""
    flags: List[str] = []
    has_desc = bool(desc.strip())
    has_ac = bool(ac.strip())
    has_user_fmt = bool(re.search(r"\bas\s+a[n]?\b.*\bi\s+(would\s+like|want|need)", desc, re.I))
    if not has_desc:
        flags.append("Description is empty.")
    elif len(desc) < 80:
        flags.append(f"Description is very short ({len(desc)} chars).")
    if not has_ac:
        flags.append("No acceptance criteria found.")
    if has_desc and not has_user_fmt and issue.issuetype.lower() == "story":
        flags.append("Description does not use 'As a ... I want ...' format.")
    if not issue.parent_epic:
        flags.append("Story is not linked to a parent epic.")
    if not flags:
        flags.append("Basic structure present (description + AC + parent).")
    return ReadinessFlags(has_desc, has_ac, has_user_fmt, flags)


def triage(issue: JiraIssue) -> Dict[str, bool]:
    """Decide which conditional prompts to run for a given issue."""
    haystack = " ".join(
        [
            issue.summary or "",
            issue.description or "",
            issue.acceptance_criteria or "",
            " ".join(issue.labels),
        ]
    ).lower()
    return {
        "edge_cases": bool(re.search(EDGE_CASE_TRIGGERS, haystack, re.I)),
        "integration": bool(re.search(INTEGRATION_TRIGGERS, haystack, re.I)),
        "slotting": bool(re.search(SLOTTING_TRIGGERS, haystack, re.I)),
    }


# ---------- LLM providers ---------------------------------------------------
class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._impl = self._make_impl()

    def _make_impl(self):
        if self.cfg.provider == "openai":
            from openai import OpenAI
            return _OpenAIChat(OpenAI(api_key=self.cfg.openai_api_key), self.cfg.openai_model)
        if self.cfg.provider == "azure":
            from openai import AzureOpenAI
            client = AzureOpenAI(
                api_key=self.cfg.azure_api_key,
                azure_endpoint=self.cfg.azure_endpoint,
                api_version=self.cfg.azure_api_version,
            )
            return _OpenAIChat(client, self.cfg.azure_deployment)
        if self.cfg.provider == "anthropic":
            from anthropic import Anthropic
            return _AnthropicChat(Anthropic(api_key=self.cfg.anthropic_api_key), self.cfg.anthropic_model)
        if self.cfg.provider == "github_models":
            from openai import OpenAI
            client = OpenAI(
                api_key=self.cfg.gh_models_token,
                base_url=self.cfg.gh_models_endpoint,
            )
            return _OpenAIChat(client, self.cfg.gh_models_model)
        raise RuntimeError(f"Unsupported provider: {self.cfg.provider}")

    def complete(self, system: str, user: str) -> str:
        return self._impl.complete(system, user)


class _OpenAIChat:
    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    def complete(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()


class _AnthropicChat:
    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    def complete(self, system: str, user: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "\n".join(parts).strip()


# ---------- orchestration ---------------------------------------------------
def _render_story_details(issue: JiraIssue) -> str:
    lines = [
        f"Key: {issue.key}",
        f"Summary: {issue.summary}",
        f"Issue Type: {issue.issuetype}",
        f"Status: {issue.status}",
        f"Priority: {issue.priority}",
        f"Labels: {', '.join(issue.labels) or '(none)'}",
        f"Parent Epic: {issue.parent_epic or '(none)'}",
    ]
    if issue.linked_issues:
        lines.append("Linked Issues:")
        lines.extend(f"  - {l}" for l in issue.linked_issues)
    lines.append("")
    lines.append("Description:")
    lines.append(issue.description.strip() or "(empty)")
    lines.append("")
    lines.append("Acceptance Criteria:")
    lines.append(issue.acceptance_criteria.strip() or "(none)")
    return "\n".join(lines)


def analyze_issue(llm: LLMClient, issue: JiraIssue) -> Dict[str, str]:
    """Run the applicable prompts and return section -> markdown analysis."""
    story_details = _render_story_details(issue)
    flags = compute_readiness_flags(issue)
    decisions = triage(issue)
    log.info("%s triage: %s", issue.key, {k: v for k, v in decisions.items() if v})

    results: Dict[str, str] = {}
    results["Core"] = llm.complete(
        prompts.SYSTEM_PROMPT,
        prompts.CORE_READINESS
        .replace("{{story_details}}", story_details)
        .replace("{{readiness_flags}}", flags.to_markdown()),
    )
    if decisions["edge_cases"]:
        results["Edge Cases"] = llm.complete(
            prompts.SYSTEM_PROMPT,
            prompts.EDGE_CASES.replace("{{story_details}}", story_details),
        )
    if decisions["integration"]:
        results["Integration"] = llm.complete(
            prompts.SYSTEM_PROMPT,
            prompts.INTEGRATION_RISK.replace("{{story_details}}", story_details),
        )
    if decisions["slotting"]:
        results["Slotting"] = llm.complete(
            prompts.SYSTEM_PROMPT,
            prompts.SLOTTING_ALLOCATION.replace("{{story_details}}", story_details),
        )
    results["QA"] = llm.complete(
        prompts.SYSTEM_PROMPT,
        prompts.QA_TESTABILITY.replace("{{story_details}}", story_details),
    )
    aggregated = "\n\n".join(f"## {name}\n{body}" for name, body in results.items())
    results["Formatted"] = llm.complete(
        prompts.SYSTEM_PROMPT,
        prompts.FORMATTER.replace("{{story_details}}", aggregated),
    )
    results["_triage"] = ", ".join(k for k, v in decisions.items() if v) or "(none)"
    results["_flags"] = flags.to_markdown()
    return results
