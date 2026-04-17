<!-- WMS Story Readiness — Production Batch 2026-04-17 -->
<!-- Each analysis is delimited by a line that starts with `===KEY:` -->

===KEY: WW-1548===
# WW-1548 — Billable Picks stuck in HOLD1 (clone of WW-244)

## 1. Core Intent
Fix a data-integrity defect where billable picks (work_type 42/43/45) enter
HOLD1 after deadlock / order errors in `usp_assign_dynamic_pick` and never
recover, causing the scanner to report "No Work Available". Target changes:
error handler reversal of HOLD1 -> HOLD, replan / split-pick logic, and
elimination of needlist-active false positives.

## 2. Edge Cases & Open Questions
1. Define the full HOLD vs HOLD1 lifecycle — which events set HOLD1, which
   reverse it, which escalate?
2. Deadlock handler scope: does the TRY/CATCH wrap the full SP or only the
   UPDATE? Partial rollback risk if t_pick_detail is updated but t_work_q
   is not.
3. Split-Pick + HOLD behaviour: when 2 of 4 legs are HOLD1 and 2 are active
   does replan process all legs or skip-and-continue?
4. Needlist active-page false positives: which query drives the page? If the
   fix only masks HOLD1 rows without clearing them, billable reporting stays
   wrong.
5. Idempotency on user retry — reuse existing work_q_id or create a new row?
6. Timezone sensitivity on `CAST(wkq.date_due AS DATE) >= CAST(GETDATE() AS
   DATE)` — server-local GETDATE vs facility TZ may drop late-shift picks.

## 3. Integration Touchpoints
- `t_pick_detail`, `t_work_q` — primary tables
- `usp_assign_dynamic_pick` — SP being modified
- Error handler module (scope of change unclear)
- WebWise Needlist Active Picks page — downstream consumer
- Billable calculation pipeline — historical rows may already be wrong
- Existing subtasks: DEV / UT / QA / CR1 / CR2 / UAT — coverage is good

## 4. Slotting Impact
None directly. However, if replan re-routes split picks across zones, verify
the replanned pick inherits the original zone to avoid cross-aisle travel.

## 5. QA Plan / Test Matrix
| # | Scenario | Expected |
|---|----------|----------|
| T1 | Force deadlock in usp_assign_dynamic_pick | PKD HOLD1 -> HOLD, work_q released |
| T2 | Inject order error mid-SP | Same as T1 |
| T3 | Normal split pick | No regression, HOLD1 never set |
| T4 | Replan on HOLD PKD | New PKD row assigned, old freed |
| T5 | Needlist Active page with historical HOLD1 | No false positives |
| T6 | Billable reporting with HOLD1 | Excluded until released |
| T7 | Reproduce INC0390552 | Matches before/after demo |
| T8 | 100 concurrent split picks | No lock escalation from retry |

## 6. Formatter / Grooming Notes
- Description contains encoding artefacts (`,%`) — clean up.
- Empty headings (`Solution Implemented`, `Proposed Solution`, `Deployment
  Artifacts`) must be populated before DEV pickup.
- No story-point value. Recommended sizing: **M (5 pts)**.
- Pull recreation steps from the SharePoint demo video into a QA prep
  checklist before sprint start.

**Verdict: Needs Clarification — moderate.** Fix intent is clear and subtasks
are in place, but error-handler scope, HOLD / HOLD1 state transitions, and
needlist query impact must be nailed down before DEV commits.

===KEY: WW-179===
# WW-179 — EDI Lost HJ Transactions (HJ -> AS400)

## 1. Core Intent
EDI transactions from HighJump to AS400 are being stranded at
`t_export_tran.status = 'E'` when the AS400 connection drops mid-write.
Story asks for:
1. Automatic retry `N` times at 10-minute intervals.
2. After `N` failures, raise a ServiceNow incident.
3. Disable the legacy automated SN ticket creation job from the EDI process.

## 2. Edge Cases & Open Questions
1. What is `N`? Not specified. Must be configurable (`t_config` row / SP
   parameter) with a documented default.
2. Retry window expiry — if AS400 is down 24h, exponential back-off or
   constant 10-min cadence? Storm risk on recovery.
3. AS400 idempotency — if a failed transaction partially wrote before the
   connection dropped, does reprocessing create duplicates? Confirm dedupe
   via EDI sequence number / `tblAudit`.
4. Asia latency — root-cause comment cites Asia as disproportionately
   affected; is 10 min appropriate globally or should interval be
   region-aware?
5. Partial message groups — multiple transactions per message; retry per
   message or per row? AC is silent.
6. ServiceNow API credentials — token storage / rotation / network path
   (on-prem WhJ -> SN cloud)?
7. Which existing job creates the "legacy" SN tickets? Must identify the
   SP / SSIS / scheduled task so it can be decommissioned safely.
8. Historical 'E' backlog — retry all historical rows or new only? Bulk
   retry could flood AS400.
9. `t_export_tran.status` enum — N, E, and what else? Need a terminal
   failure state (e.g., 'F') after N retries exhausted.
10. Audit trail — each retry attempt must log attempt #, timestamp,
    error reason; new column `retry_count` or tblAudit row?

## 3. Integration Touchpoints
- `t_export_tran` — outbound EDI queue
- `tblAudit` (EDI) — audit records
- AS400 EDI listener — confirm retry-safe
- ServiceNow API — new integration
- Existing EDI SN-ticket job — must be disabled in same release
- Network path: on-prem AS400 <-> on-prem WhJ (no cloud SB hop)

## 4. Slotting Impact
None — pure transaction-reprocessing layer.

## 5. QA Plan / Test Matrix
| # | Scenario | Expected |
|---|----------|----------|
| T1 | AS400 up, EDI succeeds first time | status -> C, no retry row |
| T2 | AS400 down for 1 retry | Reprocess after 10 min, no SN ticket |
| T3 | AS400 down for all N retries | SN incident created, status terminal |
| T4 | AS400 up but returns business error | N retries fail, SN ticket with error |
| T5 | Simulated Asia latency | No retry if tx completes before tick |
| T6 | SN API itself down | Fallback alert (email) |
| T7 | Historical 'E' backfill | Per decision from Q8 above |
| T8 | Legacy SN job disabled | No duplicate incidents |

## 6. Formatter / Grooming Notes
- AC is in description body, NOT in `customfield_10091` — move it.
- Priority = High, Frequency = 5/week, but no subtasks. Add
  DEV / UT / QA / CR1 / CR2 / UAT subtasks.
- Attached email with SN sample code — attach to the ticket for
  reproducibility.
- Recommended sizing: **L (8 pts)** — new external integration + retry
  framework + legacy decommission.

**Verdict: Needs Clarification — blocking.** Cannot commit to sprint until
`N`, backfill, SN config, and terminal-state semantics are decided.


===KEY: WW-1516===
# WW-1516 — "No Work Available" after WebWise scanner reset (Cycle Count)

## 1. Core Intent
When a user runs "SIM Reset an RF Device" (Unassign Reader) in WebWise, the
scanner session is cleared but the associated `t_work_q` assignment stays in
`Assigned`, blocking the same or another user from re-acquiring the cycle
count location. Fix: modify the `WA.SIM Reset an RF Device` Process Object
to also reset the work queue — but ONLY when the work type is Cycle Count.

## 2. Edge Cases & Open Questions
1. AC narrows reset to Cycle Count only. Why? Are picks / replens
   intentionally preserved across reset? Confirm with Operations.
2. Work-type identification — which column / value marks "cycle count"?
   `t_work_q.work_type` enum value? Must be explicit in the Process Object
   change.
3. Mid-count state — if the user already counted 3 of 5 items in a
   location, does reset lose partial results? Flush (re-count all) or
   preserve (resume from last)?
4. Lock contention / handoff — multiple users may have touched a work_q.
   Which user's assignment do we clear?
5. Concurrent reset race — Scanner A reset while Scanner B already picked
   up the re-queued cycle count. Isolation level?
6. Audit trail — reset action should write a breadcrumb (who reset, which
   scanner, which work_q) for post-incident forensics.
7. Reset semantics on the work_q row — delete, NULL the user_id, or set
   status back to `New`? Must preserve the linked cycle-count plan.
8. Scanner death via battery / network (not user-initiated reset) still
   leaves work_q assigned — out of scope, but log as follow-up story.
9. Priority = Low, Frequency = 2–3/month — scope tightly; don't
   over-engineer.

## 3. Integration Touchpoints
- WebWise Process Object `WA.SIM Reset an RF Device`
- `t_work_q` — `assigned_user_id`, `status`, `work_type`
- `t_reader` / scanner session table — existing reset already handles
- Cycle-count plan table (`t_cc_plan` or `t_count_task`) — verify linkage
- WebWise UI — no change (back-end-only)

## 4. Slotting Impact
Indirect only: stuck cycle counts compound inventory inaccuracy, which
eventually pressures slotting — not a story-level concern.

## 5. QA Plan / Test Matrix
| # | Scenario | Expected |
|---|----------|----------|
| T1 | Reset with Cycle Count assigned | work_q cleared, user re-acquires |
| T2 | Reset with Pick assigned | work_q retained (out of AC scope) |
| T3 | Reset with no work assigned | No-op, no error |
| T4 | Two users race: A reset, B picks up | B acquires cleanly, no orphan |
| T5 | Partial count before reset | Behaviour per decision in Q3 |
| T6 | Audit row after reset | Breadcrumb recorded |
| T7 | Regression: reset with no work_q | No change |

## 6. Formatter / Grooming Notes
- AC is stronger than typical (two bullets + scope-limiter) but is in the
  description body, not `customfield_10091`. Move it.
- No subtasks. Add DEV / UT / QA. CR1/CR2 optional since this is a
  Process Object change (low-risk config).
- Description has encoding artefacts in bullets.
- `Impact:` heading is empty — fill with business cost (IT intervention
  per incident, count delay).
- Ask author for the before/after Process Object XML diff.
- Recommended sizing: **S (3 pts)**.

**Verdict: Needs Clarification — minor.** Small, well-scoped change; only
partial-count behaviour and reset semantics need explicit answers.


===KEY: WW-1608===
# WW-1608 — RI 608 API Interface configuration (Raw Material)

## 1. Core Intent
Replace the legacy EDI export for Receive-for-Inspection (RI) Transaction
Type 608 with a metadata-driven JSON outbound generation mechanism,
configured through `t_api_config` and `t_api_config_transform`. Output is
one JSON file per transaction, routed by header metadata (eventType,
environmentId, companyId) to AFI / Millenium / Wanek Service Bus
subscriptions. Out of scope: the POST to MAPICS itself.

## 2. Edge Cases & Open Questions (spec itself has defects)
1. **eventType inconsistency**: AFI/MIL use
   `Ashley.Warehouse.Inspection.Recieved`, Wanek uses
   `Ashley.Warehouse.ReceiveForInspection`. Intentional (two topics)?
2. **"Recieved" misspelling** — likely copied from existing filters; confirm
   whether MAPICS / Service Bus consumers already match the misspelled
   value. Will ship if not caught.
3. **Sample JSON is malformed** — missing comma after `transactionDate`;
   `"reason":   :   "WMSRI "` has stray colon + trailing space;
   `"reference": "M0435/9"   --- Roll number` mixes a comment into JSON.
   Spec must be corrected before config work.
4. **DoD conflict**: Business Objective says legacy EDI/XML is replaced,
   but DoD says "xml data generated ... posted into t_export_xml_log".
   Clarify whether an intermediate XML stage still exists.
5. **MessageHeader arrays**: sample shows `companyId`, `environmentId`,
   `sourcesystem` as arrays. SB SQL filters `companyId = 'AFI'` will not
   match an array — header must emit scalars per transaction.
6. **correlationId** — "UUID per transaction"; confirm generator
   (`NEWID()` vs `uuid_v4`) and whether retries reuse correlationId to
   dedupe on the consumer side.
7. **Roll-level quantity trigger** — what *detects* a roll-level change?
   Trigger on `t_stored_item`? Event on `t_inspection`? Spec silent.
8. **Per-line vs per-header 608 filter** — what if an inspection has
   mixed 608 and non-608 lines?
9. **Metadata-mismatch "skip log"** — where is it written? New table
   `t_api_skip_log` or reuse `t_api_transform_log`?
10. **`eventAction`** appears in the transform but is absent from the
    payload mapping table — undefined source / rule.
11. **Environment topic names** embed env suffix; ensure deployment
    pipeline promotes the correct row (don't ship prod-topic into dev).
12. **Idempotency / retry** — if JSON emission fails mid-write, re-export
    or silently skip? Relates to WW-179 retry pattern.
13. **Macro library** — `#APIConfig(...)`, `#valueof(...)`, `#vars(...)`
    are referenced but not defined in the ticket.
14. **UTF-8 without BOM** — assert explicitly; SB consumers typically
    reject BOM-prefixed payloads.
15. **Sample date `"2026-02-30..."`** is not a real date. Fix the sample.
16. **`"M0435/9"` contains a slash** — any consumer restrictions on the
    `reference` field? Encoding rule?

## 3. Integration Touchpoints
- `t_api_config`, `t_api_config_transform` — new config rows
- `t_export_xml_log` (?) — per DoD; conflicts with JSON-only goal
- Azure Service Bus — `production-scheduling-{env}-topic` and 9 subs
- MAPICS inbound API (out of scope, downstream)
- Legacy EDI RI 608 export pipeline — **gated off for 608 only** (non-608
  tran types continue using EDI)
- WhJ transform engine macros — `#APIConfig`, `#valueof`, `#vars`

## 4. Slotting Impact
None — outbound integration.

## 5. QA Plan / Test Matrix
| # | Scenario | Expected |
|---|----------|----------|
| T1 | Valid RI 608 + AFI metadata | JSON matches schema, posted to AFI sub |
| T2 | Valid RI 608 + Wanek metadata | JSON posted to Wanek sub (diff eventType) |
| T3 | Valid RI 608 + Millenium metadata | JSON posted to MIL sub |
| T4 | RI non-608 (e.g., 607) | No JSON; legacy path still works |
| T5 | Metadata mismatch (bad companyId) | No file; skip logged |
| T6 | Missing mandatory field (whsId null) | No file; skip logged |
| T7 | Roll quantity change | File generated |
| T8 | Duplicate send (same correlationId) | Dedupe on consumer (or block at sender) |
| T9 | UTF-8 no BOM | Passes SB ingest |
| T10 | Malformed config JSON in transform | Validation fails early |
| T11 | Legacy EDI gate for 608 | No dual XML emission to t_export_xml_log |
| T12 | Correlation round-trip via MAPICS mock | Traceable back to RI tx |

Plus a **negative-contract test** with the malformed sample JSON from the
spec to prove implementation rejects it if ever regressed into the config.

## 6. Formatter / Grooming Notes
- Long spec but contains errors that will propagate to production (typos,
  malformed JSON, invalid date, header array vs scalar mismatch). Fix
  pre-DEV.
- AC in `customfield_10091` is adequate but should add:
  - Legacy EDI path disabled *only* for tran_type = 608
  - correlationId format = UUID v4
  - JSON is UTF-8 without BOM
  - Explicit AC for metadata mismatch and missing mandatory fields
- Existing subtasks: DEV / UT / QA / CR1 / CR2. Missing: UAT; also an
  ARCH review subtask given legacy deprecation.
- Ask author for: full `t_api_config_transform` payload (not sample),
  macro reference, skip-log destination.
- Recommended sizing: **L (8 pts)**.

**Verdict: Needs Clarification — moderate → blocking for production
deploy.** Spec ships defects into config if left as-is; grooming must
clean up the JSON sample, eventType alignment, and DoD conflict before
DEV picks up.

===KEY: WW-524===
# WW-524 — Hotload ship error — PKD messed up

## 1. Core Intent
`t_pick_detail` (PKD) quantities drift out of sync with `t_stored_item`
(STO) and `t_serial_active` (SNA) when Hotload ship operations run against
picks that are still mid-process with a staging user. AC narrows the fix
scope to two SPs:
1. Only assign picks for loading that are **not** still assigned to the
   staging user.
2. Loading split may split PKD records only where `user_assigned IS NULL`.

## 2. Edge Cases & Open Questions
1. Staging vs. loading user semantics — does "staging user" mean
   `pkd.staging_user_id` or a role on `t_user`? Which column identifies
   them?
2. What triggers a "Hotload"? Time-based (ship window < N min),
   flag-based (`order.hotload = 1`), or manual?
3. Race window: staging user releases just as loading tries to assign.
   Transaction isolation level of the assign SP — risk of stale
   `user_assigned` reads under READ COMMITTED.
4. Historical drift repair — if PKD is already out of sync with STO/SNA,
   does this story include data repair or only prevention? AC is silent.
5. Partial staging + partial loading split — PKD qty 100, staging locks
   40, loading wants to split 60. AC blocks the whole split. Is that
   intended, or should the 60 split off and the 40 remain with staging?
6. Reference to WW-292 (RESEARCH, Done) — recreation steps live there.
   Link the research doc officially on WW-524.
7. No subtasks. Add DEV / UT / QA / CR1 / CR2 / UAT.
8. "PKD messed up" is imprecise. AC only addresses loading assign and
   loading split SPs. Are other paths (replan, RF pick complete, bulk
   move) also candidates? State explicitly in DoD.
9. Post-fix monitor: add a verification query to AC
   (`PKD.qty vs STO.qty` across shared keys) for ongoing drift
   detection.
10. Frequency + business impact not captured on the ticket.

## 3. Integration Touchpoints
- `t_pick_detail` (PKD), `t_stored_item` (STO), `t_serial_active` (SNA)
- Loading-assign SP (name unstated; likely `usp_assign_loading_pick`)
- Loading-split SP (name unstated)
- Research ticket WW-292 — recreation steps

## 4. Slotting Impact
None directly. PKD inconsistencies may cascade to incorrect replen / slot
decisions downstream, but that is out of scope here.


## 5. QA Plan / Test Matrix
| # | Scenario | Expected |
|---|----------|----------|
| T1 | PKD with user_assigned = staging user, Hotload assigns | Blocked / deferred; no PKD qty mutation |
| T2 | PKD with user_assigned = NULL | Assignment proceeds normally |
| T3 | Loading split where user_assigned = staging user | Split blocked |
| T4 | Loading split where user_assigned = NULL | Succeeds; PKD/STO/SNA aligned |
| T5 | Reproduce WW-292 recreation steps (pre-fix) | Bug exhibits |
| T6 | Reproduce WW-292 recreation steps (post-fix) | No drift |
| T7 | Post-run monitor: PKD.qty vs STO.qty | Zero mismatches on shared keys |
| T8 | Concurrent staging release + loading assign | Eventual consistency; no double-assign |

## 6. Formatter / Grooming Notes
- Description is good but has no frequency, no impact statement, and no
  quantification of "failed allocations, manual corrections". Ask reporter.
- No subtasks — add before ticket leaves Backlog.
- AC exists in `customfield_10091` but is thin — extend with post-fix
  monitor query and historical-backfill decision.
- Priority = Medium, Status = Backlog; has been aged since sibling WW-292
  (RESEARCH) was closed. Update description to reference provenance.
- Recommended sizing: **M (5 pts)**.

**Verdict: Needs Clarification — moderate.** Research is done (WW-292)
and AC points at the right SPs, but historical-drift handling,
staging-user column semantics, and subtask / sizing setup are missing.
