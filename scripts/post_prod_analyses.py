"""Post the 2026-04-17 production-batch Story Readiness analyses to Jira.

Reads ``analyses/prod_batch_2026-04-17.md``, splits on ``===KEY: <ISSUE>===``
headers, and posts each section as a Jira comment via
:class:`story_readiness.jira_client.JiraClient`.

Run from the repo root:

    $env:JIRA_EMAIL = "<...>"; $env:JIRA_API_TOKEN = "<...>"
    ./.venv/Scripts/python.exe scripts/post_prod_analyses.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from story_readiness.config import JiraConfig  # noqa: E402
from story_readiness.jira_client import JiraClient  # noqa: E402

BATCH = Path("analyses/prod_batch_2026-04-17.md")
BASE_URL = os.getenv("JIRA_BASE_URL", "https://ashley-furniture-team.atlassian.net")
EMAIL = os.getenv("JIRA_EMAIL", "").strip()
TOKEN = os.getenv("JIRA_API_TOKEN", "").strip()

SPLIT_RE = re.compile(r"^===KEY:\s*([A-Z]+-\d+)\s*===\s*$", re.MULTILINE)


def parse_batch(text: str) -> dict[str, str]:
    """Split batch markdown into {issue_key: markdown_body}."""
    parts = SPLIT_RE.split(text)
    out: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        key = parts[i].strip()
        body = parts[i + 1].strip()
        if key and body:
            out[key] = body
    return out


def main() -> int:
    if not EMAIL or not TOKEN:
        print("ERROR: set JIRA_EMAIL and JIRA_API_TOKEN", file=sys.stderr)
        return 2
    cfg = JiraConfig(
        base_url=BASE_URL.rstrip("/"),
        email=EMAIL,
        api_token=TOKEN,
        projects=["WW", "WR"],
        label="Estimate",
        ac_field="customfield_10091",
    )
    client = JiraClient(cfg)
    sections = parse_batch(BATCH.read_text(encoding="utf-8"))
    print(f"Parsed {len(sections)} analyses from {BATCH}")
    errors: list[str] = []
    for key, body in sections.items():
        try:
            client.post_comment(key, body)
            print(f"  [OK]  {key} ({len(body):,} chars posted)")
        except Exception as exc:  # noqa: BLE001 - log & continue
            print(f"  [ERR] {key}: {exc}")
            errors.append(key)
    if errors:
        print(f"FAILED: {', '.join(errors)}", file=sys.stderr)
        return 1
    print("All analyses posted successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
