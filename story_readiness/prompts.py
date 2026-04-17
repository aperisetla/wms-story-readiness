"""The six-part WMS/HighJump Story Readiness prompt framework.

Each template contains ``{{story_details}}`` and optional ``{{readiness_flags}}``
placeholders that are filled in by :mod:`analyzer`.
"""
from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a senior WMS (Warehouse Management System) solution architect "
    "with strong knowledge of HighJump processes. Respond in neutral, "
    "constructive language. Do NOT judge individuals. Do NOT approve or "
    "reject the story. Focus on clarity, edge cases, dependencies, and "
    "testability. Use concise markdown with short bullets."
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
