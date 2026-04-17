"""Update (PUT) the latest Jira comment authored by the current user on each
key in ``analyses/prod_batch_v2_2026-04-17.md`` with the v2 gold-standard body.

Required env:
  JIRA_EMAIL, JIRA_API_TOKEN, JIRA_ACCOUNT_ID

Optional env:
  JIRA_BASE_URL (defaults to https://ashley-furniture-team.atlassian.net)
  BATCH_PATH    (defaults to analyses/prod_batch_v2_2026-04-17.md)
  DRY_RUN=1     (list what would change without touching Jira)

Usage:
  ./.venv/Scripts/python.exe scripts/update_prod_comments.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from story_readiness.config import JiraConfig  # noqa: E402
from story_readiness.jira_client import JiraClient  # noqa: E402

BASE_URL = os.getenv("JIRA_BASE_URL", "https://ashley-furniture-team.atlassian.net")
EMAIL = os.getenv("JIRA_EMAIL", "").strip()
TOKEN = os.getenv("JIRA_API_TOKEN", "").strip()
ACCOUNT_ID = os.getenv("JIRA_ACCOUNT_ID", "").strip()
BATCH = Path(os.getenv("BATCH_PATH", "analyses/prod_batch_v2_2026-04-17.md"))
DRY_RUN = os.getenv("DRY_RUN", "").strip() in {"1", "true", "yes"}

SPLIT_RE = re.compile(r"^===KEY:\s*([A-Z]+-\d+)\s*===\s*$", re.MULTILINE)


def parse_batch(text: str) -> dict[str, str]:
    parts = SPLIT_RE.split(text)
    out: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        key = parts[i].strip()
        body = parts[i + 1].strip()
        if key and body:
            out[key] = body
    return out


def pick_comment_id(comments: list[dict], account_id: str) -> str | None:
    """Return the most recent comment id authored by ``account_id``."""
    for c in comments:  # comments are already ordered -created
        author = (c.get("author") or {}).get("accountId")
        if author == account_id:
            return c.get("id")
    return None


def main() -> int:
    if not EMAIL or not TOKEN or not ACCOUNT_ID:
        print("ERROR: set JIRA_EMAIL, JIRA_API_TOKEN, JIRA_ACCOUNT_ID", file=sys.stderr)
        return 2
    if not BATCH.exists():
        print(f"ERROR: batch file not found: {BATCH}", file=sys.stderr)
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
            comments = client.list_comments(key, order_by="-created")
            cid = pick_comment_id(comments, ACCOUNT_ID)
            if not cid:
                print(f"  [SKIP] {key}: no existing comment by {ACCOUNT_ID}")
                errors.append(key)
                continue
            if DRY_RUN:
                print(f"  [DRY]  {key}: would update comment {cid} ({len(body):,} chars)")
                continue
            client.update_comment(key, cid, body)
            print(f"  [OK]   {key}: updated comment {cid} ({len(body):,} chars)")
        except Exception as exc:  # noqa: BLE001 - log and continue
            print(f"  [ERR]  {key}: {exc}")
            errors.append(key)

    if errors:
        print(f"FAILED: {', '.join(errors)}", file=sys.stderr)
        return 1
    print("All existing comments updated to gold-standard v2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
