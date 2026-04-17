"""CLI entrypoint: `python -m story_readiness`."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .analyzer import LLMClient, analyze_issue
from .config import AppConfig, load_config
from .jira_client import JiraClient, JiraIssue

log = logging.getLogger("story_readiness")


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m story_readiness",
        description="Run WMS Story Readiness analysis for Jira stories labelled 'Estimate'.",
    )
    p.add_argument("--env-file", default=None, help="Path to .env file (default: ./.env)")
    p.add_argument("--projects", default=None, help="Comma-separated project keys, overrides env")
    p.add_argument("--label", default=None, help="Jira label to filter on, overrides env")
    p.add_argument("--exclude", default=None, help="Comma-separated issue keys to skip")
    p.add_argument("--max-issues", type=int, default=None, help="Cap issues per run")
    p.add_argument("--output-dir", default=None, help="Override output directory")
    p.add_argument("--post-comments", action="store_true", help="Post analysis back to Jira (overrides env)")
    p.add_argument("--dry-run", action="store_true", help="Never post to Jira even if env says so")
    p.add_argument("--verbose", action="store_true", help="Debug logging")
    return p.parse_args(argv)


def _apply_overrides(cfg: AppConfig, args: argparse.Namespace) -> AppConfig:
    if args.projects:
        cfg.jira.projects = [x.strip() for x in args.projects.split(",") if x.strip()]
    if args.label:
        cfg.jira.label = args.label
    if args.exclude:
        cfg.runtime.exclude_keys = [x.strip() for x in args.exclude.split(",") if x.strip()]
    if args.max_issues is not None:
        cfg.runtime.max_issues = args.max_issues
    if args.output_dir:
        cfg.runtime.output_dir = Path(args.output_dir).resolve()
        cfg.runtime.output_dir.mkdir(parents=True, exist_ok=True)
    if args.post_comments:
        cfg.runtime.post_comments = True
    if args.dry_run:
        cfg.runtime.post_comments = False
    return cfg


def _format_issue_markdown(issue: JiraIssue, analysis: Dict[str, str]) -> str:
    lines = [
        f"# {issue.key} — {issue.summary}",
        "",
        f"- **Type:** {issue.issuetype}  **Status:** {issue.status}  **Priority:** {issue.priority}",
        f"- **Labels:** {', '.join(issue.labels) or '(none)'}",
        f"- **Parent:** {issue.parent_epic or '(none)'}",
        f"- **Triage:** {analysis.get('_triage', '')}",
        "",
        "## Structural Readiness Flags",
        analysis.get("_flags", ""),
        "",
        "## Grooming-Friendly Summary",
        analysis.get("Formatted", "(no formatter output)"),
        "",
        "<details><summary>Raw section analyses</summary>",
        "",
    ]
    for name in ("Core", "Edge Cases", "Integration", "Slotting", "QA"):
        if name in analysis:
            lines.extend([f"### {name}", analysis[name], ""])
    lines.append("</details>")
    return "\n".join(lines)


def _format_summary_table(rows: List[Dict[str, str]]) -> str:
    hdr = "| Key | Type | Status | Triage | Verdict |\n|---|---|---|---|---|"
    body = "\n".join(
        f"| {r['key']} | {r['type']} | {r['status']} | {r['triage']} | {r['verdict']} |"
        for r in rows
    )
    return f"{hdr}\n{body}" if rows else "_No issues found._"


def _extract_verdict(formatted: str) -> str:
    for line in formatted.splitlines():
        low = line.lower()
        if "ready" in low and "needs clarification" not in low and line.strip().startswith(("-", "*", "Ready", "**")):
            return line.strip(" -*#").strip()
        if "needs clarification" in low:
            return line.strip(" -*#").strip()
    return "(verdict not parsed)"


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = _apply_overrides(load_config(args.env_file), args)

    jira = JiraClient(cfg.jira)
    llm = LLMClient(cfg.llm)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = cfg.runtime.output_dir / f"story-readiness-{stamp}.md"
    exclude = set(cfg.runtime.exclude_keys)
    summary_rows: List[Dict[str, str]] = []
    detail_blocks: List[str] = []
    processed = 0

    log.info(
        "Scanning projects=%s label=%s post_comments=%s",
        cfg.jira.projects, cfg.jira.label, cfg.runtime.post_comments,
    )

    for raw in jira.search_estimate_issues():
        issue = jira.to_issue(raw)
        if issue.key in exclude:
            log.info("Skipping excluded %s", issue.key)
            continue
        if cfg.runtime.max_issues and processed >= cfg.runtime.max_issues:
            log.info("Reached max_issues cap (%d)", cfg.runtime.max_issues)
            break
        log.info("Analyzing %s — %s", issue.key, issue.summary)
        try:
            analysis = analyze_issue(llm, issue)
        except Exception as exc:  # pragma: no cover
            log.exception("Analysis failed for %s: %s", issue.key, exc)
            continue
        detail_blocks.append(_format_issue_markdown(issue, analysis))
        summary_rows.append({
            "key": issue.key,
            "type": issue.issuetype,
            "status": issue.status,
            "triage": analysis.get("_triage", ""),
            "verdict": _extract_verdict(analysis.get("Formatted", "")),
        })
        if cfg.runtime.post_comments:
            try:
                jira.post_comment(issue.key, analysis.get("Formatted", ""))
            except Exception as exc:  # pragma: no cover
                log.exception("Failed to post comment to %s: %s", issue.key, exc)
        processed += 1

    report = [
        f"# WMS Story Readiness Report — {stamp}",
        "",
        f"Projects: {', '.join(cfg.jira.projects)}  |  Label: {cfg.jira.label}  |  Issues analyzed: {processed}",
        "",
        "## Summary",
        _format_summary_table(summary_rows),
        "",
        "---",
        "",
        "\n\n---\n\n".join(detail_blocks) if detail_blocks else "_No issues analyzed._",
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")
    log.info("Wrote report: %s", report_path)
    print(str(report_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
