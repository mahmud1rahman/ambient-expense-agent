# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import re
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import Workflow, node
from pydantic import BaseModel

# --- Pydantic Schemas ---

class ExpenseReport(BaseModel):
    session_id: str | None = None
    amount: float
    claimant: str
    purpose: str
    description: str

class ExpenseDecision(BaseModel):
    status: str
    reason: str | None = None

class RiskAssessment(BaseModel):
    summary: str
    risk_level: str
    factors: list[str]

# --- Nodes ---

@node
def parse_expense_event(node_input: str | dict | ExpenseReport) -> Event:
    """Parses incoming event and routes based on amount."""
    if isinstance(node_input, str):
        data = json.loads(node_input)
    elif isinstance(node_input, dict):
        data = node_input
    elif isinstance(node_input, ExpenseReport):
        data = node_input.model_dump()
    else:
        raise ValueError(f"Unexpected input type: {type(node_input)}")
        
    report = ExpenseReport(**data)
    
    threshold = float(os.getenv("AUTO_APPROVE_THRESHOLD", "100.0"))
    
    if report.amount < threshold:
        return Event(output=report.model_dump(), route="auto_approve")
    else:
        return Event(output=report.model_dump(), route="needs_security_check")

@node
def auto_approve(node_input: dict[str, Any]) -> Event:
    """Instantly approves low-value expenses."""
    decision = ExpenseDecision(status="APPROVED", reason="Amount below auto-approve threshold.")
    return Event(output=decision.model_dump())

@node
def security_checkpoint(node_input: dict[str, Any]) -> Event:
    """Redacts PII and checks for prompt injections."""
    report = ExpenseReport(**node_input)
    
    # 1. Very basic PII scrubbing (simulated)
    # Redact fake SSN pattern
    report.description = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED SSN]', report.description)
    # Redact fake CC pattern
    report.description = re.sub(r'\b(?:\d{4}-){3}\d{4}\b', '[REDACTED CC]', report.description)
    
    # 2. Prompt injection detection (simulated)
    injection_keywords = ["ignore previous instructions", "system prompt", "bypass"]
    for keyword in injection_keywords:
        if keyword in report.description.lower() or keyword in report.purpose.lower():
            # Injection detected
            assessment = RiskAssessment(
                summary="Potential Prompt Injection Detected",
                risk_level="CRITICAL",
                factors=["Found injection keywords in text."]
            )
            return Event(output=assessment.model_dump(), route="injection_alert")
            
    return Event(output=report.model_dump(), route="clean")

review_risk = LlmAgent(
    name="review_risk",
    model="gemini-flash-latest",
    instruction="""You are a corporate expense risk auditor. Evaluate the expense report for policy violations, vague descriptions, or unusual spending.
Provide a risk assessment.""",
    output_schema=RiskAssessment,
)

@node
async def human_review(ctx: Context, node_input: dict[str, Any]):
    """Pauses for human review and handles decision."""
    if not ctx.resume_inputs:
        yield RequestInput(interrupt_id="human_approval", message="Please review this expense.")
        return
        
    action = ctx.resume_inputs.get("human_approval")
    
    if isinstance(action, dict) and "approved" in action:
        status = "APPROVED" if action["approved"] else "REJECTED"
    elif isinstance(action, str):
        status = action.upper()
    else:
        status = "REJECTED"
        
    decision = ExpenseDecision(status=status, reason="Manual human review decision.")
    yield Event(output=decision.model_dump())

# --- Workflow Graph Assembly ---

root_agent = Workflow(
    name="root_agent",
    edges=[
        ('START', parse_expense_event),
        (parse_expense_event, auto_approve, "auto_approve"),
        (parse_expense_event, security_checkpoint, "needs_security_check"),
        (security_checkpoint, human_review, "injection_alert"),
        (security_checkpoint, review_risk, "clean"),
        (review_risk, human_review),
    ],
    description="Ambient Expense Approval Agent Workflow",
)

app = App(
    root_agent=root_agent,
    name="app",
)
