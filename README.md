# WMS Story Readiness Analyzer

Automates the six-part WMS/HighJump Story Readiness framework against Jira
stories labelled `Estimate` in the `WW` (WMS Wholesale) and `WR` (WMS Retail)
projects.

For each issue the tool:

1. Runs the **Core Story Readiness** prompt.
2. Conditionally runs **Edge-Case**, **Integration Risk**, and
   **Slotting / Allocation** prompts based on keyword triage of the summary,
   description, acceptance criteria, and labels.
3. Runs the **QA Testability** prompt.
4. Consolidates results through the **Output Formatter** prompt into a
   grooming-ready summary with an explicit
   `Ready` / `Needs Clarification (minor | moderate | blocking)` verdict.
5. Writes a timestamped markdown report to `./output/` and, optionally, posts
   the formatted summary back as a Jira comment.

---

## Repository layout

```
Story Readiness/
├── .env.example              # environment variable template
├── .gitignore
├── requirements.txt
├── README.md                 # this file
├── output/                   # generated reports (gitignored)
└── story_readiness/
    ├── __init__.py
    ├── __main__.py           # CLI: `python -m story_readiness`
    ├── config.py             # env-var loader + validation
    ├── jira_client.py        # Jira REST client + ADF helpers
    ├── prompts.py            # the six prompt templates
    └── analyzer.py           # triage + LLM orchestration
```

---

## Prerequisites

- Python **3.10 or newer**
- Network egress to:
  - `https://<your-site>.atlassian.net`
  - your LLM provider (Azure OpenAI / OpenAI / Anthropic)
- A Jira Cloud **API token** for the service account that will run the tool
  ([create one here](https://id.atlassian.com/manage-profile/security/api-tokens))
- A service-account API key for the LLM provider

> ℹ️ The service account must have **Browse Projects** on `WW` and `WR` and,
> if comment posting is enabled, **Add Comments** permission.

---

## Local setup

### Windows (PowerShell)

```powershell
cd "C:\Users\<you>\...\Story Readiness"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env    # populate credentials and endpoint values
```

### macOS / Linux

```bash
cd /path/to/Story\ Readiness
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
${EDITOR:-vi} .env
```

---

## Configuration

All configuration is read from environment variables (or a `.env` file).
See [`.env.example`](./.env.example) for the complete list. The essentials:

| Variable | Purpose |
|----------|---------|
| `JIRA_BASE_URL` | e.g. `https://ashley-furniture-team-sandbox.atlassian.net` |
| `JIRA_EMAIL` | Atlassian login of the service account |
| `JIRA_API_TOKEN` | API token from id.atlassian.com |
| `JIRA_PROJECTS` | default `WW,WR` |
| `JIRA_LABEL` | default `Estimate` |
| `JIRA_AC_FIELD` | Acceptance-Criteria custom field id (default `customfield_10091`) |
| `LLM_PROVIDER` | `azure` (default), `openai`, or `anthropic` |
| `AZURE_OPENAI_*` | Endpoint, key, deployment, api-version (when provider is `azure`) |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | When provider is `openai` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | When provider is `anthropic` |
| `OUTPUT_DIR` | Report output directory (default `./output`) |
| `MAX_ISSUES` | Cap issues per run (0 = unlimited) |
| `EXCLUDE_KEYS` | Comma-separated keys to skip (e.g. `WW-1310`) |
| `POST_COMMENTS` | `0` (default) = markdown only; `1` = also post to Jira |

---

## Usage

```powershell
# Default: dry-run (no Jira comments), markdown report to ./output/
python -m story_readiness

# Restrict to a single project and skip already-in-flight tickets
python -m story_readiness --projects WW --exclude WW-1310

# Small pilot run, then inspect the report before going live
python -m story_readiness --max-issues 3 --verbose

# Post results back to Jira as comments (explicit opt-in)
python -m story_readiness --post-comments
```

Report files are written to `<OUTPUT_DIR>/story-readiness-YYYYMMDD-HHMMSS.md`
and the path is printed to stdout for easy shell chaining.

### Safety defaults

- `--dry-run` (no comment posting) is the default unless either
  `POST_COMMENTS=1` is set **and** `--dry-run` is not passed, **or**
  `--post-comments` is explicitly supplied.
- Issues listed in `EXCLUDE_KEYS` / `--exclude` are skipped before any LLM
  calls are made.
- Each LLM call uses `temperature=0.2` for deterministic output.

---

## Deployment to a shared terminal server

Goal: make the tool runnable by any member of the architecture team from a
single Windows terminal server without redistributing credentials.

### 1. One-time install (admin)

```powershell
# Pick a shared, readable location, e.g. D:\tools
cd D:\tools
git clone <your-internal-mirror>/story-readiness.git "Story Readiness"
cd "Story Readiness"

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

### 2. Shared service credentials

Create a dedicated Jira service account (e.g. `svc-story-readiness`) and an
Azure OpenAI key scoped to one deployment. Store them in a **machine-scoped**
`.env` file readable only by the architecture-team security group:

```powershell
# As an administrator
Copy-Item .\.env.example .\.env
notepad .env          # populate with service-account credentials
icacls .\.env /inheritance:r
icacls .\.env /grant "DOMAIN\ArchitectureTeam:(R)" /grant "SYSTEM:(F)" /grant "Administrators:(F)"
```

> Never commit `.env`. It is already listed in `.gitignore`.

### 3. Team launcher script

Place a thin wrapper on a shared `PATH` location (e.g. `D:\tools\bin`):

```powershell
# D:\tools\bin\story-readiness.ps1
& "D:\tools\Story Readiness\.venv\Scripts\python.exe" -m story_readiness @args
```

Team members then run:

```powershell
story-readiness                        # dry run, markdown only
story-readiness --projects WW          # one project
story-readiness --post-comments        # promote to Jira comments
```

### 4. Scheduled run (optional)

Use Task Scheduler to run a nightly dry-run and publish the report to a
shared drive:

```powershell
schtasks /Create /SC DAILY /TN "WMS Story Readiness" /ST 06:30 `
  /TR "powershell -ExecutionPolicy Bypass -File D:\tools\bin\story-readiness.ps1 --output-dir \\fs01\wms\story-readiness"
```

### 5. Audit & observability

- Reports include a triage line per story so reviewers can see which deep-dive
  prompts fired.
- Standard logging goes to stdout (INFO by default, `--verbose` for DEBUG).
- If `POST_COMMENTS=1`, every posted comment includes the Augment Code
  attribution footer so Jira history makes the automation obvious.

---

## Framework reference

The prompts applied by the tool are defined verbatim in
[`story_readiness/prompts.py`](./story_readiness/prompts.py):

| Prompt | When it runs |
|--------|--------------|
| `CORE_READINESS` | Always |
| `EDGE_CASES` | When summary/description mentions inventory, pick/pack/putaway, lot/serial, hold, transfer, return, exception, cycle count, wave, LPN, scanner, override |
| `INTEGRATION_RISK` | When text mentions STORIS, ERP, TMS, OMS, ProShip, carrier, EDI, API, interface, AS400, HighJump, automation, RF/scanner, ASN, printer, queue |
| `SLOTTING_ALLOCATION` | When text mentions slotting, replenishment, allocation, forward pick, casegood, dynamic slot |
| `QA_TESTABILITY` | Always |
| `FORMATTER` | Always — consolidates all of the above |

Triage rules live in `analyzer.py` (`EDGE_CASE_TRIGGERS`,
`INTEGRATION_TRIGGERS`, `SLOTTING_TRIGGERS`) and can be tuned without touching
the prompt text.

---

## Troubleshooting

- **`401 Unauthorized` from Jira** — confirm `JIRA_EMAIL` matches the account
  that created `JIRA_API_TOKEN`, and that the token hasn't expired.
- **`404` for some issues** — the service account lacks Browse Project
  permission on those projects; grant access or narrow `JIRA_PROJECTS`.
- **`Azure OpenAI configuration incomplete`** — populate all four
  `AZURE_OPENAI_*` variables or switch `LLM_PROVIDER` to `openai`.
- **Empty Acceptance Criteria in reports** — the AC field id differs between
  projects; set `JIRA_AC_FIELD` to the correct `customfield_#####` for the
  project you are analyzing.
- **Slow runs** — lower `MAX_ISSUES` or switch to a cheaper model
  (`OPENAI_MODEL=gpt-4o-mini`).
