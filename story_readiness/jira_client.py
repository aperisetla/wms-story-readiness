"""Thin Jira Cloud REST client tailored to Story Readiness workflows."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

import requests
from requests.auth import HTTPBasicAuth

from .config import JiraConfig

log = logging.getLogger(__name__)


@dataclass
class JiraIssue:
    key: str
    summary: str
    status: str
    issuetype: str
    labels: List[str]
    priority: str
    description: str
    acceptance_criteria: str
    parent_epic: str
    linked_issues: List[str]
    raw: Dict[str, Any]


class JiraClient:
    def __init__(self, cfg: JiraConfig, timeout: int = 30):
        self.cfg = cfg
        self.timeout = timeout
        self.auth = HTTPBasicAuth(cfg.email, cfg.api_token)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}

    # -- search --------------------------------------------------------------
    def search_estimate_issues(
        self, include_keys: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        if include_keys:
            keys_clause = ",".join(f'"{k}"' for k in include_keys)
            jql = f"key in ({keys_clause}) ORDER BY key DESC"
        else:
            projects = ",".join(self.cfg.projects)
            jql = (
                f'labels = "{self.cfg.label}" AND project in ({projects}) '
                f"ORDER BY key DESC"
            )
        fields = [
            "summary", "status", "labels", "priority", "issuetype",
            "description", "parent", "issuelinks", "subtasks",
            self.cfg.ac_field,
        ]
        url = f"{self.cfg.base_url}/rest/api/3/search/jql"
        next_token: Optional[str] = None
        while True:
            body: Dict[str, Any] = {
                "jql": jql,
                "fields": fields,
                "maxResults": 50,
            }
            if next_token:
                body["nextPageToken"] = next_token
            resp = requests.post(
                url, json=body, auth=self.auth, headers=self.headers, timeout=self.timeout
            )
            resp.raise_for_status()
            payload = resp.json()
            for issue in payload.get("issues", []):
                yield issue
            if payload.get("isLast", True):
                break
            next_token = payload.get("nextPageToken")
            if not next_token:
                break

    # -- normalize -----------------------------------------------------------
    def to_issue(self, raw: Dict[str, Any]) -> JiraIssue:
        f = raw.get("fields", {}) or {}
        parent_epic = ""
        parent = f.get("parent") or {}
        if parent:
            pf = parent.get("fields", {}) or {}
            parent_epic = f"{parent.get('key', '')} — {pf.get('summary', '')}".strip(" —")
        links: List[str] = []
        for lnk in f.get("issuelinks", []) or []:
            for side in ("outwardIssue", "inwardIssue"):
                other = lnk.get(side)
                if other:
                    lf = other.get("fields", {}) or {}
                    rel = lnk.get("type", {}).get("name", "relates")
                    links.append(
                        f"{rel}: {other.get('key')} ({lf.get('status', {}).get('name', '?')}) "
                        f"— {lf.get('summary', '')}"
                    )
        ac_raw = f.get(self.cfg.ac_field)
        return JiraIssue(
            key=raw.get("key", ""),
            summary=f.get("summary", "") or "",
            status=(f.get("status") or {}).get("name", "") or "",
            issuetype=(f.get("issuetype") or {}).get("name", "") or "",
            labels=f.get("labels", []) or [],
            priority=(f.get("priority") or {}).get("name", "") or "",
            description=adf_to_text(f.get("description")),
            acceptance_criteria=adf_to_text(ac_raw),
            parent_epic=parent_epic,
            linked_issues=links,
            raw=raw,
        )

    # -- comment -------------------------------------------------------------
    def post_comment(self, key: str, markdown_body: str) -> None:
        url = f"{self.cfg.base_url}/rest/api/3/issue/{key}/comment"
        body = {"body": _markdown_to_adf(markdown_body)}
        resp = requests.post(
            url, json=body, auth=self.auth, headers=self.headers, timeout=self.timeout
        )
        resp.raise_for_status()
        log.info("Posted comment to %s", key)

    def list_comments(self, key: str, order_by: str = "-created") -> List[Dict[str, Any]]:
        url = f"{self.cfg.base_url}/rest/api/3/issue/{key}/comment"
        resp = requests.get(
            url,
            params={"orderBy": order_by, "maxResults": 100},
            auth=self.auth,
            headers=self.headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("comments", []) or []

    def update_comment(self, key: str, comment_id: str, markdown_body: str) -> None:
        url = f"{self.cfg.base_url}/rest/api/3/issue/{key}/comment/{comment_id}"
        body = {"body": _markdown_to_adf(markdown_body)}
        resp = requests.put(
            url, json=body, auth=self.auth, headers=self.headers, timeout=self.timeout
        )
        resp.raise_for_status()
        log.info("Updated comment %s on %s", comment_id, key)

    def delete_comment(self, key: str, comment_id: str) -> None:
        url = f"{self.cfg.base_url}/rest/api/3/issue/{key}/comment/{comment_id}"
        resp = requests.delete(url, auth=self.auth, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        log.info("Deleted comment %s on %s", comment_id, key)


# ---------- ADF helpers -----------------------------------------------------
def adf_to_text(value: Any) -> str:
    """Flatten Atlassian Document Format (or plain string) to readable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return str(value).strip()
    parts: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        t = node.get("type")
        if t == "text":
            parts.append(node.get("text", ""))
        elif t in ("hardBreak",):
            parts.append("\n")
        elif t in ("paragraph", "heading", "listItem", "blockquote"):
            walk(node.get("content", []))
            parts.append("\n")
        elif t in ("bulletList", "orderedList"):
            for li in node.get("content", []) or []:
                parts.append("- ")
                walk(li.get("content", []))
        else:
            walk(node.get("content", []))

    walk(value)
    return "\n".join(line.rstrip() for line in "".join(parts).splitlines() if line.strip())


def _markdown_to_adf(markdown: str) -> Dict[str, Any]:
    """Wrap markdown content into a minimal ADF document using code blocks.

    Jira Cloud's native renderer does not parse full markdown, but code blocks
    preserve formatting for review. This avoids a heavyweight markdown->ADF
    conversion dependency while still producing readable comments.
    """
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "codeBlock",
                "attrs": {"language": "markdown"},
                "content": [{"type": "text", "text": markdown}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Co-authored by "},
                    {
                        "type": "text",
                        "text": "Augment Code",
                        "marks": [{
                            "type": "link",
                            "attrs": {"href": "https://www.augmentcode.com/?utm_source=atlassian&utm_medium=jira_comment&utm_campaign=jira"},
                        }],
                    },
                ],
            },
        ],
    }
