<!-- WMS Story Readiness - Production Batch v2 - 2026-04-17 -->
<!-- Gold-standard shape (matches the WR-1327 pilot comment). -->
<!-- Sections are split on lines starting with `===KEY:`. -->

===KEY: WW-1608===
### WW-1608 - Raw Material RI process - API Interface configuration - HJ
Project: WMS · Type: Story · Priority: Medium · Labels: Estimate · Parent: WW-1502 (Implement Container-Level Verification & API-Based MAPICS Sync for RI 608) · Status: Ready

**Description (as written):** Configure `t_api_config` and `t_api_config_transform` so that Receive-for-Inspection (RI) Transaction Type 608 emits a metadata-driven JSON payload to Azure Service Bus (per-tenant subscription for AFI / Millenium / Wanek), replacing the legacy EDI / XML export. Out of scope: the HTTP POST to MAPICS.
**Acceptance Criteria (as written):** RI 608 transaction matching metadata generates one JSON file per transaction in the configured outbound directory; legacy EDI export is not triggered for 608; correlationId unique per transaction; header filter split across AFI / MIL / WNK.

🟡 Missing or Unclear Details
- **Spec defects** (these will ship into `t_api_config_transform` rows if left as-is):
  - Sample JSON is malformed - missing comma after `transactionDate`; `"reason":   :   "WMSRI "` contains stray colon and trailing space; `"reference": "M0435/9"   --- Roll number` mixes an inline comment into JSON.
  - Sample date `"2026-02-30T20:00:00.340"` is not a real calendar date.
  - `MessageHeader` example shows `companyId`, `environmentId`, `sourcesystem` as **arrays**, but SB SQL filters `companyId = 'AFI'` expect scalars per message. Header must emit scalars.
  - `eventType` is inconsistent across tenants: AFI/MIL = `Ashley.Warehouse.Inspection.Recieved`, Wanek = `Ashley.Warehouse.ReceiveForInspection`. Intentional (two topics)? Also "Recieved" is misspelled throughout.
  - `eventAction` is referenced in the transform macros but absent from the payload-mapping table - source value / rule undefined.
- DoD conflict: Business Objective says legacy XML/EDI is **replaced**, but DoD says "xml data generated ... posted into t_export_xml_log". Clarify whether there is still an intermediate XML stage.
- correlationId generator not specified - `NEWID()`, `NEWSEQUENTIALID()`, or an application UUID v4? Must the same correlationId be reused on retry so the consumer dedupes?
- Macro library (`#APIConfig(...)`, `#valueof(...)`, `#vars(...)`) is referenced but not defined or linked in the ticket.
- "Skip log" destination for metadata-mismatch and missing-mandatory cases is not specified - new `t_api_skip_log` table or reuse `t_api_transform_log`?
- Existing subtasks: DEV / UT / QA / CR1 / CR2. **Missing UAT subtask**, and arguably an ARCH review subtask given the EDI deprecation.

🏭 Warehouse-Specific Edge Cases (Edge-Case Focus)
- Quantity trigger source: "roll-level quantity changes must trigger outbound" - what actually detects the change? A trigger on `t_stored_item`, an event from `t_inspection`, or a scheduled scan? Not specified.
- Mixed 608 / non-608 lines on the same inspection - per-line filter or per-header? Spec is silent.
- Partial receipt at container level - the AC emphasises container-level but does not say what happens if only 2 of 5 rolls have been inspected when the transaction fires.
- UTF-8 encoding - SB consumers typically reject BOM-prefixed payloads; must assert BOM-less UTF-8 explicitly.
- `reference = "M0435/9"` contains a slash - confirm no downstream consumer strips or rejects it.
- Re-inspection of the same roll - does the same correlationId flow through, or a fresh UUID? Consumer dedupe depends on this.
- Environment promotion: `production-scheduling-{dev|stage|prod}-topic` names must be driven by env variable at deploy, never by hardcoded config row.
- Idempotency on emission failure: if the JSON write fails mid-file, does the transaction re-export or silently skip? Related to WW-179 retry pattern - align with it.

🔌 Integration & Interface Risk - HIGH relevance
- Direct WhJ -> Azure Service Bus -> MAPICS pipeline, cross-tenant (AFI / MIL / WNK), with three different subscriptions per environment (9 subs total).
- Legacy EDI RI 608 export path must be **gated off only for 608** - non-608 tran types must continue to emit EDI unchanged.
- Header-filter driven routing is fragile: one typo in an `environmentId` value suppresses the whole tenant's messages silently.
- MAPICS side schema is out of scope, but a contract test with a MAPICS mock is mandatory to prove field order / type compatibility before go-live.
- Audit / traceability: each outbound must carry correlationId + eventType + environmentId + companyId, and must be traceable back to the source RI transaction via `t_export_xml_log` (or replacement).
- Secrets / connection strings for SB must be environment-scoped; confirm DEV config cannot post to PROD topic.

🧭 Slotting / Allocation-Specific
Not applicable - outbound integration with no inventory placement or allocation logic.

🧪 QA Testability Considerations
**Positive**
- Valid RI 608 with AFI metadata -> JSON generated matching schema; posted to `erp-afi-recieveForInspection-*-sub`.
- Valid RI 608 with Wanek metadata -> JSON posted to `erp-wnk-*`.
- Valid RI 608 with Millenium metadata -> JSON posted to `erp-mil-*`.
- Roll-level quantity change -> outbound generated; trace confirmed via correlationId.

**Negative / Exception**
- Metadata mismatch (bad companyId / environmentId) -> no file emitted; skip logged.
- Missing mandatory field (e.g., `whsId` null) -> no file emitted; skip logged.
- Malformed transform row in `t_api_config_transform` -> validation fails at config load, not at message emission.
- SB topic unreachable -> emission retries per agreed pattern; no silent drop.

**Regression**
- RI non-608 (e.g., 607) -> legacy EDI path still emits unchanged.
- Legacy EDI path for 608 -> **not** triggered once new path is enabled (dual-emit guard).
- Other `t_api_config` consumers (existing topics) -> unchanged behaviour.

**RF / Automation / Batch**
- If emission is driven by a scheduled DataPublisher job, confirm the job picks up the new tran_type filter on next cycle without restart.
- Verify no unintended latency added to the existing roll-inspection RF flow.

❓ Grooming Questions
1. Will the team fix the spec defects (malformed JSON sample, invalid Feb-30 date, header arrays vs scalars, "Recieved" misspelling, eventType mismatch) in this ticket before DEV picks it up?
2. Is the DoD line about `t_export_xml_log` a legacy carry-over or does an intermediate XML stage actually remain?
3. What is the correlationId generator, and is it reused across retries?
4. Where is the skip-log written, and what columns does it require for debugging?
5. Will a UAT subtask be added to align with the other WW- stories under WW-959?
6. Who owns the MAPICS-side contract test, and what is the agreed mock payload for CR1 / CR2?
7. Confirm: legacy EDI for 608 is disabled only after new path is verified in stage - rollback plan if SB is unreachable?

✅ Verdict: Needs Clarification (moderate)
Spec is rich but contains ship-ready defects in the sample JSON and header model; DoD conflict and missing UAT subtask must be resolved before sprint commit.


===KEY: WW-1548===
### WW-1548 - Billable Picks stuck in HOLD1 (clone of WW-244, PRB1365630)
Project: WMS · Type: Story · Priority: Medium · Labels: Estimate · Parent: WW-959 (PRBs 2026 Q2) · Status: Ready · Links: *clones* WW-244 (Done)

**Description (as written):** Users cannot pick and the scanner shows "No Work Available" because billable picks (`t_work_q.work_type IN ('42','43','45')`) are getting stuck in `t_pick_detail.status = 'HOLD1'` after deadlocks or order errors hit `usp_assign_dynamic_pick`. Workaround today is a pick replan. Subtasks cover DEV / UT / QA / CR1 / CR2 / UAT.
**Acceptance Criteria (as written):** (1) Handle and reverse HOLD1 -> HOLD in the error handler (deadlock, order errors). (2) Validate replan logic when PKD is in HOLD status during Split Pick in `usp_assign_dynamic_pick`. (3) Ensure picks are not updated to HOLD status incorrectly, showing false positives on the needlist active pages.

🟡 Missing or Unclear Details
- Full lifecycle of HOLD vs HOLD1 is not documented on the ticket - which events transition a pick into HOLD1, which reverse it, and which escalate further? A state diagram is required before DEV commits.
- Error-handler scope is ambiguous: does the `TRY/CATCH` wrap the entire SP or only the `UPDATE t_pick_detail`? Partial rollback risk if PKD is updated but `t_work_q` is not.
- Split-pick behaviour when HOLD1 coexists with active legs: if two legs go HOLD1 and two stay active, does replan reprocess all legs or skip-and-continue?
- "False positives on needlist active pages" - which query drives the active page? A mask-only fix (hiding HOLD1 rows in the UI query) will still leave billable reporting wrong downstream.
- Idempotency on user retry: after reversal, is the same `work_q_id` reused or is a new row created? Not specified.
- Timezone on the validation query (`CAST(wkq.date_due AS DATE) >= CAST(GETDATE() AS DATE)`) uses server-local GETDATE(); if the WhJ server time zone differs from the facility's, late-shift picks may drop off the filter.
- Description has several empty headings (`Solution Implemented`, `Proposed Solution`, `Deployment Artifacts`, `Processes Impacted`) - populate before DEV pickup.
- No story-point value visible.

🏭 Warehouse-Specific Edge Cases (Edge-Case Focus)
- Deadlock injected mid-SP: both PKD and work_q must either commit together or roll back together - validate under the isolation level actually used by WhJ.
- Concurrent split-pick storms: 100+ dynamic assigns running at once when a facility starts shift - verify the reversal loop does not escalate locks or cause retry storms.
- Billable flag + HOLD1: historical PKD rows already flagged billable while HOLD1 may have polluted billing / KPIs; decide whether a one-time cleanup query is in scope.
- Replan on HOLD PKD: AC 2 asks for validation, not new behaviour - confirm whether behaviour change is expected or just coverage.
- Needlist Active page regression: if masking HOLD1 rows changes the row count, any KPIs or shift-lead dashboards fed by that page may drift.
- User handoff: a picker who leaves the facility with a PKD in HOLD1 - does the next picker see the recovered PKD on login, or is it orphaned?

🔌 Integration & Interface Risk - LOW relevance
- No external system involved. All changes are internal to WhJ SQL (`t_pick_detail`, `t_work_q`, `usp_assign_dynamic_pick`) plus the WebWise Needlist Active Picks UI query.
- Billable export (downstream consumer) is indirectly affected - confirm whether billable reports include historical HOLD1 rows and whether they need a retroactive correction.

🧭 Slotting / Allocation-Specific
Not applicable - defect operates below location slotting. If replan re-routes a split pick across zones, verify it inherits the original zone to avoid cross-aisle travel spikes, but no slotting algorithm is changed.

🧪 QA Testability Considerations
**Positive**
- Normal split pick completes with no HOLD1 set - baseline unchanged.
- Replan on a PKD in HOLD -> new PKD row assigned, old freed, PKD/STO aligned.
- Reproduce INC0390552 using `usp_incident_capture 'INC0390552','0017954-00',''` and confirm the recorded before/after demo matches the fix.

**Negative / Exception**
- Force a deadlock in `usp_assign_dynamic_pick` (concurrent split-pick assigns on the same work_q) -> PKD HOLD1 reverts to HOLD and `t_work_q` is released atomically.
- Inject an order error mid-SP -> same reversal as deadlock case, no orphan rows.
- Needlist Active page with historical HOLD1 rows -> no false positives after deploy.
- Billable reporting -> PKD rows still in HOLD1 are excluded until explicitly released.

**Regression**
- `usp_assign_dynamic_pick` under normal load (no error injected) -> no behaviour change for non-HOLD1 paths.
- Non-billable work types -> behaviour unchanged.
- Pick replan path -> unchanged for non-HOLD PKD rows.

**RF / Automation / Batch**
- Scanner "No Work Available" screen: verify the user gets a work item on next poll after a reversal without needing re-login.
- Shift-start bulk assign: 100 concurrent split picks under the new TRY/CATCH - confirm no lock escalation and p95 SP runtime is within current SLA.

❓ Grooming Questions
1. Is the scope of the error handler change the whole SP or only the critical UPDATE block? Need a clear diff target.
2. Does this story include a one-time cleanup for historically stuck HOLD1 PKDs, or is that a separate PRB?
3. Should the needlist active-page query be changed in the same release, or is that a follow-up UI ticket?
4. Is there a billable-reporting impact window (i.e., does Finance need to reconcile prior months after the fix)?
5. What is the current isolation level of `usp_assign_dynamic_pick`, and should it change?
6. Can we get a story-point estimate attached before planning?

✅ Verdict: Needs Clarification (moderate)
Root cause is well-identified and subtask coverage is strong, but error-handler scope, needlist-query impact, and the historical-cleanup decision must be nailed down before DEV commits.


===KEY: WW-1516===
### WW-1516 - "No Work Available" after WebWise scanner reset during Cycle Count (PRB0041667)
Project: WMS · Type: Bug · Priority: Low · Labels: Estimate · Parent: WW-959 (PRBs 2026 Q2) · Status: To Do · Frequency: 2-3 incidents / month

**Description (as written):** When a user runs WebWise "Unassign Reader" / SIM Reset of an RF Device while a cycle-count work_q is assigned, the scanner session clears but `t_work_q.status` remains `Assigned`, blocking the same or another user from re-acquiring the location. Proposed fix: modify the `WA.SIM Reset an RF Device` Process Object to also reset the work queue.
**Acceptance Criteria (as written):** When a scanner is reset via WebWise Unassign Reader, the associated work_q data should reset and not remain in 'Assigned' state **only when the work queue is a cycle count**; update `WA.SIM Reset an RF Device` to include the automatic work-queue reset logic.

🟡 Missing or Unclear Details
- Acceptance Criteria are in the description body, not in `customfield_10091`. Move them.
- No subtasks. Add DEV / UT / QA. CR1 / CR2 optional since the change is a Process Object configuration (low-risk).
- Work-type identification is not explicit - which column and value define "cycle count" (`t_work_q.work_type` code)?
- "Reset" semantics on the work_q row are ambiguous: delete the row, NULL the `assigned_user_id`, or set `status` back to `New`? Must preserve the linked cycle-count plan.
- Partial-count state is undefined: if the user already counted 3 of 5 items in a location, does reset flush the partial (re-count all) or preserve it (resume from last)?
- `Impact:` heading is empty - fill with business cost (IT intervention per incident, count delay, possible inventory-accuracy drift).
- No before/after Process Object diff attached.

🏭 Warehouse-Specific Edge Cases (Edge-Case Focus)
- Scanner dies via battery or network drop (not user-initiated reset) leaves work_q assigned by the same mechanism - out of scope here, but raise as a follow-up story.
- Two-user race: Scanner A is reset while Scanner B has already picked up the re-queued cycle count - which user wins, and what isolation level governs the transition?
- Shift handoff: the original assignee has logged out; the next user scans in and should see the location available again.
- Multiple active cycle-count plans for the same location (rare but possible during re-counts) - which plan does the reset target?
- Audit trail: the reset action should leave a breadcrumb (who reset, which scanner, which work_q) to support post-incident forensics.
- Frequency is low (2-3 / month) and priority is Low - keep scope tight; do not over-engineer.

🔌 Integration & Interface Risk - LOW relevance
- All changes are internal to WebWise (`WA.SIM Reset an RF Device` Process Object) and WhJ (`t_work_q`, `t_reader`, cycle-count plan table).
- No external system is involved.
- Confirm the Process Object change propagates to all facilities on deploy and that there is a rollback path (revert the Process Object to prior version).

🧭 Slotting / Allocation-Specific
Not applicable directly. Stuck cycle counts compound inventory inaccuracy over time, which eventually pressures slotting, but that is a downstream effect, not a story-level concern.

🧪 QA Testability Considerations
**Positive**
- Reset scanner with a cycle-count work_q assigned -> work_q cleared; the same user can re-acquire immediately.
- Another user scans into the same location after the reset -> location is available.

**Negative / Exception**
- Reset scanner with a Pick or Replen work_q assigned -> work_q is **retained** (out of AC scope).
- Reset scanner with no work assigned -> no-op, no SQL error.
- Two users race on the same location: A reset, B picks up - B acquires cleanly, no orphan rows.
- Partial count before reset -> behaviour per the decision taken in grooming (flush vs resume).

**Regression**
- Existing scanner reset flows for non-cycle-count work types -> unchanged.
- RF login / logoff flow -> unchanged.
- Cycle-count plan header -> unchanged by the work_q reset.

**RF / Automation / Batch**
- RF scan of a just-reset cycle-count location -> user sees correct prompts and can proceed with the count.
- Audit / event log shows the reset event tied to a user, scanner, and work_q record.

❓ Grooming Questions
1. What is the specific `work_type` value (or values) that identifies "cycle count" for the reset predicate?
2. What should the reset do to the work_q row - delete, null the assignee, or revert status? Confirm with a Process Object diff.
3. If a partial count exists, does the reset discard it or preserve it?
4. Can we add an audit entry for every reset (user, scanner, work_q_id, timestamp) so operations can trace repeats?
5. Any objection to scoping DEV / UT / QA only (no CR1 / CR2 or UAT), given this is a Process Object configuration change?
6. Story-point estimate - is S (3 pts) appropriate?

✅ Verdict: Needs Clarification (minor)
Small, well-scoped change with a clear AC. Only partial-count behaviour, reset semantics, and the exact work_type predicate need explicit answers; move the AC into `customfield_10091` and add subtasks before sprint commit.

===KEY: WW-524===
### WW-524 - Hotload ship error - PKD messed up (PRB0040975)
Project: WMS · Type: Story · Priority: Medium · Labels: Estimate · Parent: WW-959 (PRBs 2026 Q2) · Status: Backlog · Links: *relates to* WW-292 (Done, RESEARCH)

**Description (as written):** `t_pick_detail` (PKD) quantities drift out of sync with `t_stored_item` (STO) and `t_serial_active` (SNA) when Hotload ship operations run against picks that are still mid-process with a staging user. The drift causes failed allocations, incorrect pick tasks, and manual corrections by support. Sibling ticket WW-292 (Done) holds the research / recreation steps.
**Acceptance Criteria (as written):** (1) Only assign picks for loading that are not still assigned to the staging user. (2) Loading split can only split PKD records where `user_assigned IS NULL`. (3) Use the recreation steps from the attached research document to test before and after fix.

🟡 Missing or Unclear Details
- "Staging user" is defined by convention, not by column: is it `pkd.staging_user_id`, a role flag on `t_user`, or a join to the staging work-queue table? Must be explicit in the SP diff.
- Hotload trigger is undefined - time-based (ship window < N minutes), flag-based (`order.hotload = 1`), or manual override?
- Historical drift repair: PKD rows already out of sync with STO / SNA may still exist. Is a one-time cleanup / reconciliation query in scope, or only prevention?
- Partial staging + partial loading split: PKD qty 100, staging locks 40, loading wants to split 60. AC 2 blocks the whole split on non-null `user_assigned`. Is that intended, or should the 60 split off while staging keeps the 40?
- No subtasks. Add DEV / UT / QA / CR1 / CR2 / UAT.
- Research provenance: the ticket links to WW-292 via `relates to`. Update the description to name WW-292 as the research phase so it is visible without hovering the link.
- Monitor query: AC 3 refers to recreation steps, but there is no standing drift-detection query to leave in place post-fix. Consider adding one to the AC.
- Frequency and business impact are not captured on the ticket.

🏭 Warehouse-Specific Edge Cases (Edge-Case Focus)
- Race window: staging user releases (`user_assigned <- NULL`) in the same millisecond that loading tries to assign. Isolation level of the assign SP matters - READ COMMITTED can read stale `user_assigned`.
- Hotload bypass of staging: if a shipment qualifies as hotload and staging is skipped entirely, does AC 1 still apply, or is that a different code path?
- Serialized vs bulk picks: SNA only exists for serial-tracked items; PKD drift on non-serial items is detectable only via STO. Confirm both cases are exercised in QA.
- Replan, RF pick-complete, bulk-move: these SPs can also desync PKD vs STO / SNA. AC only addresses loading assign + loading split - is that the full scope?
- Staging user absent / terminated: `user_assigned` references a user no longer in `t_user`. Does the blocker still apply, or should it unblock?
- Multi-line orders with partial staging completion: some lines staged, others not - loading assigns by line, not by order - confirm behaviour.

🔌 Integration & Interface Risk - LOW relevance
- All changes are internal to WhJ SQL (`t_pick_detail`, `t_stored_item`, `t_serial_active`, and the loading assign / split SPs).
- No external system involved.
- Downstream consumers (ship manifests, billing, carrier BOLs) depend on accurate PKD; verify no regression in manifest generation.

🧭 Slotting / Allocation-Specific
Not applicable directly. PKD-STO drift can cascade into incorrect replen or slot decisions downstream, but that impact is out of scope for this story.

🧪 QA Testability Considerations
**Positive**
- PKD with `user_assigned IS NULL` -> loading assignment proceeds; no PKD qty mutation against STO / SNA.
- Loading split on a PKD with `user_assigned IS NULL` -> split succeeds; post-split PKD + STO + SNA remain aligned.
- Reproduce WW-292 recreation steps (pre-fix) -> bug exhibits as captured.
- Reproduce the same steps (post-fix) -> no drift observed.

**Negative / Exception**
- PKD with `user_assigned` = staging user and a Hotload attempts to assign -> blocked or deferred; no PKD qty mutation, no orphan row.
- Loading split where `user_assigned` = staging user -> split blocked.
- Concurrent staging-release + loading-assign race -> eventual consistency; no double-assign.
- Order with cancelled lines + partially staged lines -> behaviour per decision in grooming.

**Regression**
- Non-hotload ship flows -> unchanged.
- Non-staging loading assign (pure loading work) -> unchanged.
- Replan / RF pick-complete / bulk-move paths -> unchanged by this story.

**RF / Automation / Batch**
- Post-run monitor query: `SELECT ... FROM t_pick_detail p JOIN t_stored_item s ON ... WHERE p.qty <> s.qty` returns zero rows on shared keys after a hotload day.
- Daily shift-end report confirms zero drift across the facility.

❓ Grooming Questions
1. Which column identifies the staging user, and is it nullable today?
2. What triggers "Hotload" semantically - a flag, a time window, or an operator action?
3. Is a one-time historical cleanup in scope, or only prevention going forward?
4. On AC 2, should partial splits be allowed (split only the un-locked qty) or blocked outright?
5. Should the fix also harden replan / RF pick-complete paths, or is WW-524 narrowly the loading assign and split SPs?
6. Can we embed a standing drift-detection query into the AC so operations has a monitor post-fix?
7. Can we get WW-292 (research) officially cross-linked as the provenance for this story?

✅ Verdict: Needs Clarification (moderate)
Research is done and AC targets the right SPs, but staging-user column semantics, historical-drift handling, and subtask / sizing setup are missing.


===KEY: WW-179===
### WW-179 - EDILostHJTransactions - Lost HJ transactions from HJ to AS400
Project: WMS · Type: Bug · Priority: High · Labels: Estimate · Parent: WW-959 (PRBs 2026 Q2) · Status: To Do · Frequency: ~5 / week

**Description (as written):** EDI transactions from HighJump (WhJ) to AS400 are being stranded in `t_export_tran.status = 'E'` when the AS400 connection drops mid-write. Manual remediation today is to set `status = 'N'` so the record re-queues. The ticket asks for: (1) automatic retry N times at 10-minute intervals; (2) after N failures, raise a ServiceNow incident; (3) disable the legacy automated SN-ticket creation job that runs from the EDI process.
**Acceptance Criteria (as written):** `(none in customfield_10091)` - requirements are in the description body.

🟡 Missing or Unclear Details
- AC field is empty; all requirements sit in the description. Move them into `customfield_10091` before sprint commit.
- No subtasks. Add DEV / UT / QA / CR1 / CR2 / UAT - priority is High.
- **N is not specified.** Must be configurable (new `t_config` row or SP parameter) with a documented default (suggestion: 3 attempts -> 30 min before escalation).
- Retry cadence semantics: constant 10-min interval, or exponential back-off after repeated failures? Storm risk when AS400 recovers.
- AS400 idempotency on re-send: if the failed transaction partially wrote before the connection dropped, does reprocessing create duplicates? Confirm dedupe via EDI sequence number / `tblAudit`.
- Legacy SN-ticket creation job: the specific SP / SSIS / scheduled task name that must be disabled is not on the ticket. Without that, the fix may double-raise incidents.
- Historical 'E' backlog: do we retry historical rows on deploy, or only new ones? A bulk retry could flood AS400.
- Terminal failure state: after N retries, should `t_export_tran.status` pin to a new value (e.g., 'F') so the retry loop does not pick it up again? Current enum is not documented.
- Audit trail per attempt: retry_count column on `t_export_tran`, or row-per-attempt in `tblAudit`?
- ServiceNow API contract: endpoint, token source, rotation process, and payload template are referenced via an attached email but not attached to the ticket itself.
- Regional latency: root-cause comment calls out Asia as disproportionately affected - is the 10-min interval appropriate there, or should cadence be region-aware?

🏭 Warehouse-Specific Edge Cases (Edge-Case Focus)
- Connection drops mid-batch when multiple transactions are being written together: retry per-row or per-batch? The choice changes idempotency guarantees on AS400.
- AS400 returns a business-error status (not a network drop) - retry or escalate immediately? Retrying business errors wastes cycles and masks data problems.
- ServiceNow API itself unreachable when escalation fires: secondary alert path (email, Teams webhook) so the failure is not silently lost.
- Retry + operator manual reset race: operator sets `status = 'N'` mid-retry - must not produce duplicate sends to AS400.
- Deploy-time switchover: the legacy SN-ticket job and the new ServiceNow incident path must be flipped atomically, otherwise the same failure produces zero or two incidents.
- 5 incidents per week baseline - after fix, measure: near-zero SN incidents means the network layer stabilised; sustained SN incidents means AS400 or schema issues.

🔌 Integration & Interface Risk - HIGH relevance
- Direct WhJ -> AS400 EDI pipeline is the core integration risk. Any change to retry semantics must preserve AS400 idempotency.
- New ServiceNow API integration: credential storage, rotation, and network path from on-prem WhJ to SN cloud must be documented.
- Legacy SN-ticket job decommission: confirm no other downstream consumer depends on it (e.g., dashboards counting tickets).
- Observability: a dashboard (or at least a query) showing retry attempts, terminal failures, and SN incidents raised per day is mandatory - without it the new behaviour is a black box.
- Rollback: if the new retry loop misbehaves, operators need a feature flag to revert to the legacy path quickly.

🧭 Slotting / Allocation-Specific
Not applicable - pure transaction-reprocessing / messaging layer.

🧪 QA Testability Considerations
**Positive**
- AS400 up, EDI transaction succeeds first time -> `status` -> completion state, no retry row, no SN incident.
- AS400 transiently down for one retry -> reprocess after 10 minutes, success on attempt 2, no SN incident.

**Negative / Exception**
- AS400 down for all N retries -> terminal failure state set, exactly one ServiceNow incident created with attempt history and last error.
- AS400 up but returns a business error - all N retries fail with the same error, SN incident created with error payload.
- ServiceNow API down at escalation time -> fallback alert (email / webhook) fires; retry SN creation on next tick.
- Operator sets `status = 'N'` mid-retry -> no duplicate AS400 send.
- Simulated Asia latency -> retry does not fire if a pending attempt completes after timeout but before the retry tick.

**Regression**
- Happy-path EDI transactions -> unchanged timing and behaviour.
- Non-AS400 export targets driven by the same framework -> unchanged.
- Legacy SN-ticket creation job -> disabled exactly once, with no orphan scheduled runs.

**RF / Automation / Batch**
- Scheduled retry job runs on its own schedule and does not block or delay the primary EDI send.
- Post-deploy monitoring: SN incident volume trend, terminal-failure count, average retries-to-success.

❓ Grooming Questions
1. What is the value of N, and where is it configured? Suggested default: 3.
2. Retry cadence: constant 10-min or back-off after first failure?
3. Do we retry the historical 'E' backlog on deploy, or quarantine it?
4. What is the terminal failure state value on `t_export_tran` after N exhaustions?
5. Which existing job creates the legacy SN tickets, and how do we disable it in the same release?
6. Where are the ServiceNow API credentials stored, and what is the rotation plan?
7. Do we need region-aware retry intervals (shorter in NA, longer in Asia), or keep 10 min globally?
8. Observability: can we commit to a basic dashboard as part of this story?

✅ Verdict: Needs Clarification (blocking)
High-priority, frequent failure with solid root cause, but cannot be committed until N, terminal-state semantics, legacy-job decommission target, and ServiceNow configuration are decided. AC also needs to move into `customfield_10091` and subtasks must be added.

===KEY: WR-1164===
### WR-1164 - WR Direct Ship/Transfer - API for QIS and Highjump for Retail
Project: WMS Retail · Type: Story · Priority: Medium · Labels: Estimate · Parent: WR-799 (WR Direct Ship/Transfer from RDC) · Status: Backlog

**Description (as written):** Establish a WhJ -> QIS API pair so that Retail direct-ship / transfer flows out of an RDC can (1) trigger inspection tickets in QIS on arrival at the RDC and (2) receive inspection results back into WhJ (with the item moved to an in-transit location) before onward transfer. Existing interfaces: `receivingSheet` and `receivingSheetClose`; per the description these do not currently exist for QIS and need to be modified.
**Acceptance Criteria (as written):** Outbound to QIS: includes tracking, item, PO, location, ingestion date, pack slips; must support single or multi items. Inbound from QIS: inspection details received, item moves to an in-transit location, defects flagged at item level, ticket closed to hand off back to WhJ. Existing `receivingSheet` and `receivingSheetClose` must be modified to support this flow.

🟡 Missing or Unclear Details
- Scope verb collision: the ticket text says the interfaces "do not currently exist" and then says "receivingSheet / receivingSheetClose must be modified". Clarify - is this *new* interface work, or an *extension* of an existing one?
- Pack slip payload shape: "pack slips" is listed but not specified - is it a PDF attachment, a structured JSON line list, or a reference to an external document store?
- Multi-item bundling: "single or multi items" - one outbound call per item, or one call per shipment with a line array? Batch semantics drive idempotency.
- Defect model on inbound: "defects flagged at item level" - what are the allowed defect codes? Is there an existing enum on WhJ, or does QIS own the taxonomy?
- In-transit location: where is the destination bin configured - per facility, per item, or globally on a `t_config` row?
- Ticket closure semantics: does QIS close its own ticket and emit the closure event, or does WhJ close it on receipt of the inbound? Race risk if both sides close independently.
- Transport layer: HTTPS REST, Azure Service Bus topic, or the same EDI/JSON pipeline as WW-1608? Unstated.
- Auth: API key, OAuth client credentials, or mTLS? Credential storage / rotation?
- Retry / idempotency: if QIS is unreachable on outbound, does WhJ queue and retry (like WW-179), or drop?
- No subtasks on the ticket. Add DEV / UT / QA / CR1 / CR2 / UAT at minimum.
- Priority is Medium, Status is Backlog - confirm this is not blocking the WR-799 parent epic.

🏭 Warehouse-Specific Edge Cases (Edge-Case Focus)
- Partial receipt at RDC: 8 of 10 items arrive - does the outbound fire now with 8, or wait for the balance? Depends on whether QIS tickets are per-shipment or per-item.
- Mixed-pack LPN: a single LPN carrying multiple SKUs across multiple orders - outbound payload needs a clear primary key to avoid QIS de-dupe collisions.
- Defective vs damaged-in-transit: QIS may flag defective on arrival, but some defects are carrier-induced. Does the defect code distinguish, and does the downstream flow differ?
- Hold / quarantine location: if QIS returns "failed inspection", should WhJ place the item in a quarantine slot distinct from in-transit, or the same?
- Re-inspection after repair: an item failed, was reworked, and needs re-inspection. Does this re-trigger the outbound, and does the previous QIS ticket reopen or does a new one get created?
- Cross-border transfer: if the shipment moves between tax jurisdictions, does the inspection hand-off carry the jurisdiction metadata?
- High-volume RDC: at 500+ inbound shipments per day, the outbound throughput must be tested to confirm QIS can accept the load.

🔌 Integration & Interface Risk - HIGH relevance
- New WhJ <-> QIS bidirectional API layer: schema design, auth, transport, and versioning all need explicit decisions before DEV.
- Modification of the existing `receivingSheet` / `receivingSheetClose` interfaces is risky: confirm no non-QIS consumer relies on the current shape.
- Downstream STORIS visibility: when the item moves to in-transit after inspection, STORIS needs to reflect the new status. Is that covered by an existing WhJ -> STORIS message, or is that a follow-up?
- Retry + dead-letter: must align with the retry pattern proposed in WW-179 so WR does not reinvent the framework.
- Audit / traceability: each outbound and inbound must be logged with a correlationId tying the QIS ticket to the WhJ receiving record.
- Observability: the ticket needs a dashboard-style requirement, not just "it works".

🧭 Slotting / Allocation-Specific
Partial relevance. The in-transit location for post-inspection items is a slotting decision: one shared in-transit bin per facility, or a pool by item type? Confirm during grooming so the bin topology is agreed before DEV.

🧪 QA Testability Considerations
**Positive**
- Inbound shipment at RDC -> outbound to QIS with all mandatory fields (tracking, item, PO, location, ingestion date, pack slip reference); QIS accepts and creates a ticket.
- QIS returns inspection results with no defects -> WhJ moves the items to the in-transit location and closes the local ticket.
- Multi-item shipment -> single outbound call carries all items; QIS returns one consolidated inspection result per line.

**Negative / Exception**
- QIS unreachable on outbound -> message queued and retried per the agreed retry framework; no lost shipment.
- QIS returns "inspection failed" with defect codes -> items flagged at item level; does NOT advance to in-transit.
- Malformed QIS inbound (missing ticket id) -> inbound rejected with a clear error, nothing mutated in WhJ.
- Duplicate QIS inbound (same correlationId) -> idempotent; second message is a no-op.
- Partial receipt scenario -> behaves per the decision made in grooming.

**Regression**
- Legacy `receivingSheet` / `receivingSheetClose` consumers (non-Retail, non-QIS) -> unchanged behaviour.
- Non-RDC receiving flows -> unchanged.
- STORIS visibility of receipts -> unchanged unless explicitly in scope.

**RF / Automation / Batch**
- RF receipt at RDC triggers outbound automatically - no manual step for the operator.
- Scheduled retry job picks up queued outbounds within the agreed SLA.

❓ Grooming Questions
1. Is this new interface work or an extension of the existing `receivingSheet` - what is the actual diff target?
2. Outbound transport: REST, Service Bus, or EDI? Same stack as WW-1608?
3. What is the defect taxonomy, and who owns it?
4. How is the in-transit location configured, and is there a separate quarantine location for failed inspections?
5. Retry / idempotency / dead-letter - align with the WW-179 pattern?
6. Does STORIS need an update when the item moves to in-transit, or is that a follow-up?
7. Who is the QIS side owner, and has a contract test been agreed?
8. Can we get subtasks added and a sizing estimate on the story?

✅ Verdict: Needs Clarification (moderate)
AC is directionally clear but the story mixes "new" and "modify" language, leaves transport / auth / defect taxonomy / retry pattern open, and has no subtasks. These gaps must close before DEV picks it up.

===KEY: WR-925===
### WR-925 - BOM parent/child item on import
Project: WMS Retail · Type: Story · Priority: Medium · Labels: Estimate · Parent: WR-734 (BOM in WhJ) · Status: Ready

**Description (as written):** Ensure Bill-of-Materials (BOM) parent/child item relationships are correctly created and maintained in WhJ when items are imported, so that inventory, receiving, picking, and shipping behave correctly for kit / BOM items in the Retail flow.
**Acceptance Criteria (as written):** `(none in customfield_10091)` - no structured AC is attached; description is a one-line summary.

🟡 Missing or Unclear Details
- Description is effectively one line. Before sizing, the ticket needs:
  - Source of the import: which upstream system sends the parent/child records (SKU master, ERP, external file drop)?
  - Import mechanism: nightly SSIS job, real-time API, manual CSV upload in WebWise?
  - Target tables in WhJ: is BOM stored in `t_item_bom` (or equivalent), and what is the parent/child column model?
  - Conflict rules: what happens when the import sends a relationship that already exists with a different quantity or child set?
- Status is "Ready" but there is no `customfield_10091` content and no visible subtasks. Cannot be Ready without an AC.
- Sibling parent WR-734 ("BOM in WhJ") is the umbrella epic - confirm which sibling stories cover BOM receipt, BOM pick, and BOM ship so WR-925 scope is properly fenced.
- Definition of "correctly": is the import expected to *create* new BOM rows, *update* existing ones, or *reconcile* (delete + recreate)?
- Kit lifecycle: does a parent auto-explode into children on receipt, or only on pick? Depends on the BOM semantics already agreed in the parent epic.
- Cancellation / deletion: if the upstream system deletes a BOM, does the import delete it in WhJ, or flag inactive?
- Audit: is there an import log capturing which rows were added, updated, or skipped?
- No story-point estimate is attached.

🏭 Warehouse-Specific Edge Cases (Edge-Case Focus)
- Recursive BOMs: parent A has child B which itself is a BOM (nested kit) - is recursion supported, and to what depth?
- Partial kits: a parent with 5 children where only 3 arrive - does the import still establish the relationship, and how does receiving handle it?
- Quantity multiplier: child qty per parent - e.g., a chair kit uses 4 identical legs - verify the import carries the multiplier and that it flows to pick/ship.
- Unit-of-measure mismatch: parent in EA, child in PAIR - conversion rules?
- Item not yet in WhJ: the import references a child SKU that has not been created in `t_item` yet - hold, skip, or fail?
- Effective dating: a BOM change scheduled for next week - does the import support date-effective versions, or is it always "active now"?
- Retail flows vs WMS flows: Retail may have different BOM semantics than wholesale (e.g., customer-visible vs internal). Confirm the scope is Retail-only.
- Concurrency: if two imports run back-to-back with different versions of the same BOM, which wins?

🔌 Integration & Interface Risk - MEDIUM relevance
- Upstream source system (unspecified) must be confirmed; changing the import spec may require coordination with that owner.
- Downstream consumers of BOM in WhJ (picking, receiving, shipping) must handle the imported relationships correctly. Verify which flows already consume the BOM tables today.
- If the import is a replacement of an existing legacy job, confirm the decommission path and dual-run window.
- Observability: an import run summary (rows read, rows written, rows skipped, errors) is mandatory for any production rollout.

🧭 Slotting / Allocation-Specific
Indirect relevance. Kit / BOM items may drive specific slotting decisions (e.g., place children adjacent to the parent to reduce pick travel). Not in scope of this ticket, but flag for the parent epic if not already covered.

🧪 QA Testability Considerations
**Positive**
- Import a brand-new parent with 3 children -> WhJ creates the parent item, 3 child items (if not yet present), and the BOM relationship rows.
- Import an existing BOM with no changes -> import is idempotent; no duplicate rows created.
- Import an existing BOM with a changed child quantity -> WhJ reflects the updated quantity.

**Negative / Exception**
- Child SKU not present in WhJ -> import behaviour per the decision in grooming (hold vs skip vs fail).
- Circular BOM (parent A references B which references A) -> import rejects with a clear error.
- UoM mismatch between parent and child -> import rejects or applies the documented conversion rule.
- Delete/inactivate flow -> upstream sends a "remove" marker, WhJ marks the relationship inactive (not hard-delete, unless decided otherwise).

**Regression**
- Non-BOM item imports -> unchanged.
- Existing BOM rows not touched by the current import run -> untouched.
- Picking / receiving / shipping flows on non-BOM items -> unchanged.

**RF / Automation / Batch**
- Scheduled import runs on its existing cadence, emits a run summary, alerts on repeated failures.
- Spot-check: a freshly imported BOM is pickable on an RF flow immediately, without a WhJ restart.

❓ Grooming Questions
1. What is the source and transport of the import (SSIS / API / file drop)?
2. Which table(s) store BOM in WhJ today, and what is the parent/child column shape?
3. Insert-only, update-in-place, or reconcile-with-delete? Must be explicit in the AC.
4. How are missing child SKUs handled - hold, skip, or fail the row?
5. Are nested BOMs supported, and to what depth?
6. Is there a date-effective version model, or is "active now" the only state?
7. Can we get an AC drafted in `customfield_10091` and subtasks added before sprint commit?
8. Should a run summary / import log table be included in the DoD?

✅ Verdict: Needs Clarification (blocking)
Status is "Ready" but the ticket is effectively a single-sentence description with no structured AC, no subtasks, and no source-system definition. It cannot enter a sprint until an AC and scope boundary are written.
