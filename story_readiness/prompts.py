"""The WMS/HighJump Story Readiness prompt framework.

``UNIFIED_READINESS`` is the single-call prompt used by :mod:`analyzer` to
produce the gold-standard grooming comment (WR-1327 shape). The older
per-section templates are retained below for backward compatibility with
tooling that still drives the multi-call flow.

All templates use ``{{story_details}}`` and optional ``{{readiness_flags}}``
placeholders.
"""
from __future__ import annotations

import re

SYSTEM_PROMPT = (
    "You are a senior WMS (Warehouse Management System) solution architect "
    "with deep knowledge of HighJump / WhJ, WebWise, STORIS, MAPICS, AS400 "
    "EDI, and Azure Service Bus integrations used at Ashley Furniture. "
    "Use WhJ vocabulary when grounded by the ticket: tables such as "
    "t_pick_detail (PKD), t_work_q, t_stored_item (STO), t_serial_active "
    "(SNA), t_export_tran, tblAudit; stored procedures prefixed usp_*; "
    "WebWise Process Objects (e.g. WA.SIM Reset an RF Device); work-queue "
    "states (New / Assigned / HOLD / HOLD1). Tone is neutral and "
    "constructive; never judge individuals and never declare the story "
    "approved or rejected. Stay grounded in what the ticket actually says "
    "- flag missing detail rather than inventing it."
)

CORE_READINESS = """You are reviewing a WMS user story for readiness before sprint planning.

Context:
- The system supports warehouse operations such as receiving, putaway, picking, packing,
  shipping, billing, and inventory management.
- The solution integrates with external systems (ERP, TMS, OMS, automation, carriers).
- Operational accuracy and data consistency are critical.

User Story Details:
{{story_details}}

Structural Readiness Checks:
{{readiness_flags}}

Tasks:
1. Identify missing or unclear functional details specific to warehouse operations.
2. Highlight potential edge cases related to inventory, order flow, or warehouse execution.
3. Identify integration or downstream dependency risks.
4. Suggest clarification questions Dev and QA should raise during grooming.
5. Indicate whether the story appears Ready or Needs Clarification.
"""

EDGE_CASES = """You are analyzing a WMS user story for operational edge cases.

Focus specifically on warehouse execution scenarios such as:
- Partial inventory availability
- Backorders and short picks
- Lot, serial, or batch-controlled inventory
- Multi-location or multi-warehouse behavior
- Exception handling during picking, packing, or shipping

Story Context:
{{story_details}}

Tasks:
1. List warehouse-specific edge cases that may not be explicitly covered.
2. Highlight scenarios that could cause inventory mismatch or operational blockage.
3. Suggest questions to clarify expected system behavior in these scenarios.
"""

INTEGRATION_RISK = """You are reviewing a WMS story with external integrations.

Typical integrations include ERP, TMS, OMS, automation systems, RF devices, and
carrier services.

Story Details:
{{story_details}}

Tasks:
1. Identify integration touchpoints involved in this story.
2. Highlight risks related to data timing, failures, retries, or mismatches.
3. Identify what should happen if an upstream or downstream system is unavailable.
4. Suggest validation or fallback scenarios QA should test.
"""

QA_TESTABILITY = """You are a QA lead specializing in warehouse systems.

Based on the story details below, identify test considerations.

Story Details:
{{story_details}}

Tasks:
1. Identify positive test scenarios.
2. Identify negative and exception scenarios relevant to WMS flows.
3. Suggest regression areas that could be impacted.
4. Highlight scenarios that may require RF, automation, or batch processing validation.
"""

SLOTTING_ALLOCATION = """You are reviewing a WMS story related to slotting, allocation,
or replenishment logic.

Story Details:
{{story_details}}

Tasks:
1. Identify edge cases related to inventory thresholds, replenishment triggers, or
   allocation rules.
2. Highlight scenarios where preconditions may not be met.
3. Suggest how the system should behave when slotting rules cannot be applied.
4. Identify downstream impacts on picking or replenishment tasks.
"""

FORMATTER = """Consolidate the analyses below into a grooming-friendly summary.

Format exactly with these top-level sections (use markdown headings):
### Missing or unclear details
### Warehouse-specific edge cases
### Integration or dependency risks
### QA considerations
### Questions for grooming discussion
### Verdict

In the Verdict section, state exactly one of:
- "Ready"
- "Needs Clarification (minor)"
- "Needs Clarification (moderate)"
- "Needs Clarification (blocking)"
followed by a one-line justification.

Keep the tone constructive and concise. Avoid technical jargon where possible.
Do not duplicate content across sections.

Source analyses (may include any subset of Core, Edge Cases, Integration,
Slotting, QA):
{{story_details}}
"""


# ---------------------------------------------------------------------------
# Unified (single-call) prompt - gold standard shape
# ---------------------------------------------------------------------------

REQUIRED_SECTIONS: tuple[str, ...] = (
    "Missing or Unclear Details",
    "Warehouse-Specific Edge Cases",
    "Integration & Interface Risk",
    "Slotting / Allocation-Specific",
    "QA Testability Considerations",
    "Grooming Questions",
    "Verdict",
)

VERDICT_LINE_RE = re.compile(
    r"^.*Verdict\s*:\s*(Ready|Needs Clarification\s*\((minor|moderate|blocking)\))",
    re.IGNORECASE | re.MULTILINE,
)


def validate_unified_output(text: str) -> list[str]:
    """Return a list of human-readable problems in a unified-prompt output.

    The returned list is empty when the output is acceptable. Callers may use
    this to decide whether to re-prompt the model with a fix-up instruction.
    """
    problems: list[str] = []
    missing = [s for s in REQUIRED_SECTIONS if s.lower() not in text.lower()]
    if missing:
        problems.append("Missing sections: " + ", ".join(missing))
    if not VERDICT_LINE_RE.search(text):
        problems.append(
            "Verdict line must match 'Verdict: Ready' or "
            "'Verdict: Needs Clarification (minor|moderate|blocking)'"
        )
    return problems



UNIFIED_READINESS = """You are reviewing a single WMS user story for sprint readiness.
Produce ONE grooming comment using the exact skeleton below. Every emoji
heading must appear, in this order, even if the content is "Not applicable".

Depth rules (adapt length to the ticket, do not pad):
- Bug / small config change -> 3-6 bullets per section.
- New feature or spec with a code / JSON / SQL snippet -> 8-15 bullets in
  Missing Details + Edge Cases, plus a "Spec Defects" sub-list that calls
  out typos, malformed JSON, conflicting statements, invalid dates.
- If the ticket touches an external system (ERP, TMS, OMS, STORIS, MAPICS,
  AS400, ServiceNow, Azure Service Bus, RF devices, automation, carriers)
  expand Integration & Interface Risk to >=6 bullets; otherwise 2-3.
- Slotting / Allocation is N/A for most integration or messaging fixes -
  if so, write one line: "Not applicable - <why>." and stop.
- Reference concrete WhJ artifacts when the ticket supplies them (table
  names, SP names, Process Object names, work_type codes). Do NOT invent
  identifiers the ticket does not provide.
- If the ticket has subtasks in inconsistent states (parent To Do with
  child In Progress, missing DEV/UT/QA/CR1/CR2/UAT coverage, cloned
  sibling already Done) flag it in Missing or Unclear Details.

Story Details:
{{story_details}}

Structural Readiness Flags:
{{readiness_flags}}

Output this exact skeleton (keep the emoji and heading text verbatim):

### <KEY> - <one-line summary>
<meta line: Project | Type | Priority | Labels | Parent | Status>

**Description (as written):** <1-3 sentences summarising the ticket body>
**Acceptance Criteria (as written):** <verbatim AC or "(none in customfield_10091)">

🟡 Missing or Unclear Details
- bullet
- bullet

🏭 Warehouse-Specific Edge Cases (Edge-Case Focus)
- bullet
- bullet

🔌 Integration & Interface Risk - <HIGH | MEDIUM | LOW> relevance
- bullet
- bullet

🧭 Slotting / Allocation-Specific
- bullet (or: "Not applicable - <reason>.")

🧪 QA Testability Considerations
**Positive**
- bullet
**Negative / Exception**
- bullet
**Regression**
- bullet
**RF / Automation / Batch** *(include only if relevant)*
- bullet

❓ Grooming Questions
1. question
2. question

✅ Verdict: <Ready | Needs Clarification (minor) | Needs Clarification (moderate) | Needs Clarification (blocking)>
<one-line justification>

Rules:
- The line starting with the white-check emoji MUST be exactly one of the
  four allowed verdict strings, followed by a single justification line.
- Do NOT output anything before the '### <KEY>' line or after the
  justification line.
- Do NOT use tables in QA Testability; keep sub-headings + bullets.
- Do NOT repeat the story description verbatim beyond the 1-3 sentence
  "Description (as written)" summary.
- Keep language neutral and constructive.
"""

