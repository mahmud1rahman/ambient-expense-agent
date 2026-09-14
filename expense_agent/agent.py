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

import base64
import json
import os
from typing import Any, Optional

from dotenv import load_dotenv

# Ensure .env variables are loaded into os.environ before ADK initialization
load_dotenv()
if os.getenv("GOOGLE_CLOUD_PROJECT") and "GOOGLE_CLOUD_PROJECT" not in os.environ:
    os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT")

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Edge, Workflow
from google.genai import types

from expense_agent.config import AUTO_APPROVE_THRESHOLD, MODEL_NAME
from expense_agent.models import (
    ExpenseDecision,
    ExpenseReport,
    RiskAssessment,
)
from expense_agent.security import detect_prompt_injection, scrub_pii


def parse_expense_event(node_input: Any, ctx: Optional[Any] = None) -> Event:
    """Parses incoming JSON or Pub/Sub event and routes based on dollar threshold.

    - Amount < $100 -> auto_approve
    - Amount >= $100 -> needs_security_check
    """
    raw_payload = node_input

    # Extract text from types.Content if passed from START
    if isinstance(raw_payload, types.Content):
        text_parts = [p.text for p in raw_payload.parts if p.text]
        raw_payload = text_parts[0] if text_parts else "{}"

    # Parse JSON string if payload is str
    if isinstance(raw_payload, str):
        try:
            raw_payload = json.loads(raw_payload)
        except Exception:
            if ctx and hasattr(ctx, "state") and "expense" in ctx.state:
                raw_payload = ctx.state["expense"]
            else:
                raw_payload = {}

    # Handle Pub/Sub message wrapping under "data"
    if isinstance(raw_payload, dict) and "data" in raw_payload:
        data_val = raw_payload["data"]
        if isinstance(data_val, str):
            parsed = None
            try:
                decoded = base64.b64decode(data_val.encode("utf-8")).decode("utf-8")
                if decoded.startswith("{ amount"):
                    decoded = decoded.replace("{ amount", '{"amount')
                try:
                    parsed = json.loads(decoded)
                except Exception:
                    import ast
                    parsed = ast.literal_eval(decoded)
            except Exception:
                pass

            if not isinstance(parsed, dict):
                try:
                    parsed = json.loads(data_val)
                except Exception:
                    pass

            if isinstance(parsed, dict):
                raw_payload = parsed
        elif isinstance(data_val, dict):
            raw_payload = data_val

    if not isinstance(raw_payload, dict) or "amount" not in raw_payload:
        if ctx and hasattr(ctx, "state") and "expense" in ctx.state:
            raw_payload = ctx.state["expense"]

    expense = ExpenseReport(**raw_payload)

    # Threshold routing in Python code (no LLM)
    if expense.amount < AUTO_APPROVE_THRESHOLD:
        return Event(
            output=expense.model_dump(),
            state={"expense": expense.model_dump()},
            route="auto_approve",
        )
    else:
        return Event(
            output=expense.model_dump(),
            state={"expense": expense.model_dump()},
            route="needs_security_check",
        )


def auto_approve(node_input: dict) -> Event:
    """Auto-approves expenses under $100 instantly without LLM involvement."""
    expense = ExpenseReport(**node_input)
    decision = ExpenseDecision(
        status="APPROVED",
        decision_by="AUTO_APPROVE",
        reason=f"Auto-approved: Amount ${expense.amount:.2f} is under threshold ${AUTO_APPROVE_THRESHOLD:.2f}",
        expense=expense,
    )
    return Event(
        output=decision.model_dump(),
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=f"Instant Auto-Approval: Expense of ${expense.amount:.2f} for {expense.category} approved."
                )
            ],
        ),
    )


def security_checkpoint(node_input: dict) -> Event:
    """Security Checkpoint:

    1. Scrubs PII (SSNs, Credit Cards) from description.
    2. Detects prompt injection attempts.
       - If injection detected -> routes to 'injection_alert' (bypasses LLM reviewer straight to human).
       - If clean -> routes to 'clean' (proceeds to LLM risk reviewer).
    """
    expense = ExpenseReport(**node_input)

    # 1. Scrub PII
    sanitized_desc, redactions = scrub_pii(expense.description)
    expense.description = sanitized_desc
    expense.redactions.extend(redactions)

    # 2. Prompt Injection Defense
    has_injection = detect_prompt_injection(sanitized_desc)

    if has_injection:
        security_risk = RiskAssessment(
            summary="SECURITY ALERT: Prompt Injection attempt detected in expense description. Bypassing LLM reviewer.",
            risk_level="HIGH",
            risk_factors=["Prompt Injection Pattern Detected in Description"],
            flagged_for_review=True,
            security_event=True,
        )
        return Event(
            output={
                "expense": expense.model_dump(),
                "risk_assessment": security_risk.model_dump(),
            },
            state={
                "expense": expense.model_dump(),
                "risk_assessment": security_risk.model_dump(),
            },
            route="injection_alert",
        )

    # Clean expense moves forward to LLM risk assessment
    return Event(
        output=expense.model_dump(),
        state={"expense": expense.model_dump()},
        route="clean",
    )


# LLM Risk Reviewer Node using gemini-3.1-flash-lite
review_risk = LlmAgent(
    name="review_risk",
    model=MODEL_NAME,
    instruction="""You are a corporate expense risk auditor.
Analyze the expense report provided in the input.
Check for risk factors such as high amounts, vague descriptions, weekend dates, or policy non-compliance.
Produce a structured RiskAssessment with summary, risk_level (LOW, MEDIUM, HIGH, CRITICAL), risk_factors list, and flagged_for_review bool.""",
    output_schema=RiskAssessment,
    output_key="risk_assessment",
)


async def human_review(ctx: Context, node_input: Any):
    """Human-in-the-Loop Node:

    Pauses workflow via RequestInput for human approval or rejection,
    then records the final outcome decision.
    """
    # Normalize input data depending on predecessor node payload
    expense_data = None
    risk_data = None

    if isinstance(node_input, dict):
        if "expense" in node_input:
            expense_data = node_input["expense"]
            risk_data = node_input.get("risk_assessment")
        elif "amount" in node_input or "submitter" in node_input:
            expense_data = node_input
        elif "summary" in node_input or "risk_level" in node_input:
            risk_data = node_input
    elif hasattr(node_input, "model_dump"):
        dumped = node_input.model_dump()
        if "amount" in dumped:
            expense_data = dumped
        elif "summary" in dumped:
            risk_data = dumped

    if not expense_data and "expense" in ctx.state:
        expense_data = ctx.state["expense"]

    if not risk_data and "risk_assessment" in ctx.state:
        risk_data = ctx.state["risk_assessment"]

    expense = (
        ExpenseReport(**expense_data) if isinstance(expense_data, dict) else expense_data
    )
    risk_assessment = (
        RiskAssessment(**risk_data) if isinstance(risk_data, dict) else risk_data
    )

    # Step 1: If human response not yet received, yield RequestInput interrupt
    if not ctx.resume_inputs or "human_approval" not in ctx.resume_inputs:
        redaction_note = (
            f" (Redacted PII: {', '.join(expense.redactions)})"
            if expense and expense.redactions
            else ""
        )
        security_note = (
            "\n⚠️ SECURITY ALERT: Prompt injection attempt detected in submission! Bypassed LLM reviewer."
            if risk_assessment and risk_assessment.security_event
            else ""
        )
        risk_summary = (
            risk_assessment.summary if risk_assessment else "Requires Manager Approval"
        )

        prompt_msg = (
            f"Approval Required for Expense of ${expense.amount:.2f} by {expense.submitter} ({expense.category}).\n"
            f"Description: '{expense.description}'{redaction_note}\n"
            f"Risk Level: {risk_assessment.risk_level if risk_assessment else 'MEDIUM'}\n"
            f"Risk Summary: {risk_summary}{security_note}\n"
            f"Please respond with 'approve' or 'reject'."
        )

        yield RequestInput(interrupt_id="human_approval", message=prompt_msg)
        return

    # Step 2: Human response received upon resume
    user_response = ctx.resume_inputs["human_approval"]
    response_str = str(user_response).strip().lower()

    if "approve" in response_str or response_str == "yes":
        status = "APPROVED"
        reason = f"Approved by human reviewer. User response: {user_response}"
    else:
        status = "REJECTED"
        reason = f"Rejected by human reviewer. User response: {user_response}"

    decision = ExpenseDecision(
        status=status,
        decision_by="HUMAN_APPROVER",
        reason=reason,
        risk_assessment=risk_assessment,
        expense=expense,
    )

    yield Event(
        output=decision.model_dump(),
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=f"Human Review Completed: Expense status set to {status}. Reason: {reason}"
                )
            ],
        ),
    )


from google.adk.workflow import START, FunctionNode, Workflow

# Wrap functions as explicit FunctionNodes
node_parse_expense_event = FunctionNode(func=parse_expense_event, name="parse_expense_event")
node_auto_approve = FunctionNode(func=auto_approve, name="auto_approve")
node_security_checkpoint = FunctionNode(func=security_checkpoint, name="security_checkpoint")
node_human_review = FunctionNode(func=human_review, name="human_review")

# Graph Workflow Definition
root_agent = Workflow(
    name="expense_approval_workflow",
    edges=[
        Edge(from_node=START, to_node=node_parse_expense_event),
        Edge(from_node=node_parse_expense_event, to_node=node_auto_approve, route="auto_approve"),
        Edge(from_node=node_parse_expense_event, to_node=node_security_checkpoint, route="needs_security_check"),
        Edge(from_node=node_security_checkpoint, to_node=review_risk, route="clean"),
        Edge(from_node=node_security_checkpoint, to_node=node_human_review, route="injection_alert"),
        Edge(from_node=review_risk, to_node=node_human_review),
    ],
)

os.environ["OTEL_SDK_DISABLED"] = "true"

app = App(
    name="app",
    root_agent=root_agent,
)
