"""Ad-hoc: read prod_issues.json and print cleaned description + AC for each."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from story_readiness.jira_client import adf_to_text as _adf_to_text  # type: ignore

RAW = Path("prod_issues.json").read_text(encoding="utf-8-sig")
BUNDLE = json.loads(RAW)

for key, raw_issue_str in BUNDLE.items():
    issue = json.loads(raw_issue_str)
    f = issue["fields"]
    print("=" * 90)
    print(f"KEY: {key}")
    print(f"TYPE: {f['issuetype']['name']} | STATUS: {f['status']['name']} | "
          f"PRIORITY: {f.get('priority',{}).get('name','?')}")
    print(f"SUMMARY: {f['summary']}")
    print(f"LABELS: {f.get('labels', [])}")
    parent = f.get("parent")
    if parent:
        print(f"PARENT: {parent['key']} - {parent['fields']['summary']}")
    subs = f.get("subtasks", []) or []
    if subs:
        print("SUBTASKS:")
        for s in subs:
            sf = s["fields"]
            print(f"  - {s['key']} [{sf['issuetype']['name']}, {sf['status']['name']}] {sf['summary']}")
    links = f.get("issuelinks", []) or []
    if links:
        print("LINKS:")
        for l in links:
            if "outwardIssue" in l:
                t = l["outwardIssue"]; d = f" -> {l['type']['outward']}"
            elif "inwardIssue" in l:
                t = l["inwardIssue"]; d = f" <- {l['type']['inward']}"
            else:
                continue
            print(f"  {d} {t['key']} [{t['fields']['status']['name']}] {t['fields']['summary']}")
    print("-" * 90)
    print("DESCRIPTION:")
    desc_adf = f.get("description")
    print(_adf_to_text(desc_adf) if desc_adf else "(none)")
    print("-" * 90)
    print("ACCEPTANCE CRITERIA (customfield_10091):")
    ac_adf = f.get("customfield_10091")
    print(_adf_to_text(ac_adf) if ac_adf else "(none)")
    print()
