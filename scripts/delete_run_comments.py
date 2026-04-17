"""Delete the most-recent Jira comment authored by the current user on each
key in ``--keys``, optionally bounded by ``--after`` / ``--before`` timestamps.

Intended use: remove the duplicate LLM comments created by a specific
GitHub Actions workflow run, leaving the earlier manual v2 comment in place.

Required env:
  JIRA_EMAIL, JIRA_API_TOKEN, JIRA_ACCOUNT_ID

Optional env:
  JIRA_BASE_URL (default: https://ashley-furniture-team.atlassian.net)
  DRY_RUN=1     (list what would change without touching Jira)

Args:
  --keys        Comma-separated Jira keys. Required.
  --after ISO   Only consider comments created at/after this ISO-8601 ts.
  --before ISO  Only consider comments created strictly before this ISO-8601 ts.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from story_readiness.config import JiraConfig  # noqa: E402
from story_readiness.jira_client import JiraClient  # noqa: E402

BASE_URL = os.getenv("JIRA_BASE_URL", "https://ashley-furniture-team.atlassian.net")
EMAIL = os.getenv("JIRA_EMAIL", "").strip()
TOKEN = os.getenv("JIRA_API_TOKEN", "").strip()
ACCOUNT_ID = os.getenv("JIRA_ACCOUNT_ID", "").strip()
DRY_RUN = os.getenv("DRY_RUN", "").strip() in {"1", "true", "yes"}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pick_target(comments: list[dict], account_id: str, after: datetime | None, before: datetime | None) -> str | None:
    for c in comments:  # ordered -created by list_comments
        author = (c.get("author") or {}).get("accountId")
        if author != account_id:
            continue
        created = _parse_ts(c.get("created"))
        if after and created and created < after:
            continue
        if before and created and created >= before:
            continue
        return c.get("id")
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--keys", required=True, help="Comma-separated Jira keys")
    p.add_argument("--after", help="ISO-8601 timestamp, e.g. 2026-04-17T15:00:00-04:00")
    p.add_argument("--before", help="ISO-8601 timestamp, e.g. 2026-04-17T16:00:00-04:00")
    args = p.parse_args(argv)

    if not EMAIL or not TOKEN or not ACCOUNT_ID:
        print("ERROR: set JIRA_EMAIL, JIRA_API_TOKEN, JIRA_ACCOUNT_ID", file=sys.stderr)
        return 2

    after = _parse_ts(args.after)
    before = _parse_ts(args.before)
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]

    cfg = JiraConfig(
        base_url=BASE_URL.rstrip("/"),
        email=EMAIL,
        api_token=TOKEN,
        projects=["WW", "WR"],
        label="Estimate",
        ac_field="customfield_10091",
    )
    client = JiraClient(cfg)
    errors: list[str] = []

    for key in keys:
        try:
            comments = client.list_comments(key, order_by="-created")
            cid = pick_target(comments, ACCOUNT_ID, after, before)
            if not cid:
                print(f"  [SKIP] {key}: no matching comment by {ACCOUNT_ID} in window")
                continue
            if DRY_RUN:
                print(f"  [DRY]  {key}: would delete comment {cid}")
                continue
            client.delete_comment(key, cid)
            print(f"  [OK]   {key}: deleted comment {cid}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERR]  {key}: {exc}")
            errors.append(key)

    if errors:
        print(f"FAILED: {', '.join(errors)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
