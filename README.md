# WMS Story Readiness

Automated grooming assistant for WMS user stories on Jira. Scans tickets in
the `WW` (WMS Wholesale) and `WR` (WMS Retail) projects that carry the
`Estimate` label, runs each one through a six-part readiness framework (Core
intent / Edge cases / Integration risk / Slotting / QA / Formatter) using
GitHub Models, and posts the resulting analysis back to Jira as a comment
with an explicit verdict
(`Ready` / `Needs Clarification (minor|moderate|blocking)`).

Target audience: BAs, WMS architects, QA leads, and grooming facilitators at
Ashley Furniture. Developers: see the *Developer reference* section at the
bottom and the inline docstrings in `story_readiness/`.

## At a glance

- **Hosted on**: GitHub Actions in `aperisetla/wms-story-readiness` (will
  move to an org-owned repo).
- **Trigger today**: manual only via `workflow_dispatch`. A scheduled and/or
  Jira-webhook trigger is planned.
- **Comment authorship**: currently the user whose token drives the run. A
  dedicated `wms-readiness-bot` service account is planned so comments
  appear under a bot identity rather than an individual.
- **Secrets**: `JIRA_EMAIL`, `JIRA_API_TOKEN` in GitHub Actions secrets. No
  separate model key is needed (the workflow uses GitHub Models via the
  built-in `GITHUB_TOKEN`).

## Running it manually

1. Open the repo on GitHub and go to **Actions > Story Readiness > Run
   workflow**.
2. Set the inputs:

   | Input           | Typical value       | Meaning                                             |
   |-----------------|---------------------|-----------------------------------------------------|
   | `projects`      | `WW,WR`             | Comma-separated project keys to scan                |
   | `exclude`       | `WW-1310`           | Comma-separated keys to skip (pilot, hotfixes, ...) |
   | `max_issues`    | `0`                 | Per-project cap; `0` = unlimited                    |
   | `post_comments` | `true` / `false`    | `true` posts to Jira; `false` only uploads a report |

3. Click **Run workflow**. A run completes in 30-90 s at current volume.
4. Download the **`readiness-reports`** artifact from the run summary to see
   every generated comment plus a summary table.

Spot-check tip: set `max_issues=1` and `post_comments=false` when validating
a prompt change - one ticket per project, no Jira writes.

## Interpreting the verdict

Every comment ends with a single `Verdict:` line. Treat it as an entry point
for the grooming conversation, not as an approval gate.

| Verdict                                | Meaning                                                                                              | Suggested action                                                                               |
|----------------------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| `Ready`                                | Ticket has clear intent, AC, subtasks (where expected), and no blocking integration unknowns.        | Size it, commit to a sprint.                                                                   |
| `Needs Clarification (minor)`          | Small gaps (missing impact text, a single ambiguous bullet).                                         | Resolve inline during grooming - 5 minutes of conversation. Do not block commit.               |
| `Needs Clarification (moderate)`       | Several gaps across AC / edge cases / subtasks; answerable in one grooming session with the author.  | Carry the questions into grooming; do not commit until answered.                               |
| `Needs Clarification (blocking)`       | Missing a critical input (e.g., external endpoint contract, an `N` value, terminal-state semantics).| Send back to the reporter for spec work; cannot be committed to a sprint in current shape.     |

The comment above the verdict always contains a numbered **Grooming Questions**
section - bring those verbatim into the grooming call.

## Output locations

- **Jira comment**: one per Estimate-labeled ticket in `WW` / `WR`. Posted
  as the user whose token drives the run (to become the service-account
  identity once that is provisioned).
- **GitHub Actions artifact**: `readiness-reports` on each run - a single
  markdown file with every comment body and a verdict summary table.
- **Hand-curated gold standard**: `analyses/prod_batch_v2_*.md` in the repo
  is the reference example set used to calibrate the prompt; not produced
  automatically by the workflow.

## Rotating the Jira service-account token

Once `wms-readiness-bot` is provisioned (owned by the platform team),
rotate its API token on a 90-day cadence or on staff change.

1. Sign in to Atlassian as `wms-readiness-bot` and open
   **Account settings > Security > API tokens**.
2. Click **Create API token**, label it `github-actions-YYYY-MM`, and copy
   the value once (it is never shown again).
3. In GitHub, open **Settings > Secrets and variables > Actions** on this
   repo (or on the org, if the secret is stored at org level).
4. Click `JIRA_API_TOKEN > Update`, paste the new value, save.
5. **Revoke** the previous token in the Atlassian UI.
6. Trigger a `workflow_dispatch` run with `max_issues=1` and
   `post_comments=false` to verify the new token before the next
   scheduled run.

The same procedure applies to `JIRA_EMAIL` (changes only on account rename).

## Current limitations

- **No idempotency check yet**: repeated runs with `post_comments=true` can
  produce duplicate comments. Workaround: add already-handled tickets to
  the `exclude` input until the marker-based idempotency check lands.
- **No auto-trigger yet**: the workflow runs only on manual dispatch.
  See the *Operational backlog* section.
- **Prompt defects surface in output**: the model is instructed to flag
  spec defects (malformed JSON, typos, conflicting statements) in the
  ticket it is reviewing, but it cannot catch every case. Treat the
  comment as a first draft, not a final review.

## Operational backlog

Tracked separately; listed here so the team knows what is next.

- Move the repo to an Ashley Furniture GitHub org.
- Provision `wms-readiness-bot` Jira user and migrate the token.
- Add a bot-signature marker + idempotency check to the posting step.
- Add a scheduled trigger (every 30 min) and, if Atlassian admin approves,
  a Jira Automation webhook for real-time runs on label-add.
- Slack / Teams summary of each run.

## Developer reference

- Source layout: see `story_readiness/` (entry point: `python -m
  story_readiness`).
- Prompt: `story_readiness/prompts.py` (`UNIFIED_READINESS` is the
  production template; older per-section templates are preserved behind
  the `--legacy-multi-call` flag).
- Output validation: `validate_unified_output()` checks that every
  required emoji section is present and that the verdict line matches
  the allowed enum. Currently advisory (logs a warning) - make it strict
  once the prompt is stable.
- Scripts: `scripts/post_prod_analyses.py`, `scripts/update_prod_comments.py`,
  `scripts/delete_run_comments.py` (ad-hoc comment maintenance; not wired
  into the scheduled pipeline).
- Contact / escalation: WMS Architecture team (internal).

