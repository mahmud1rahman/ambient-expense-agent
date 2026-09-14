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

from pydantic import BaseModel, Field


class ExpenseReport(BaseModel):
    """Pydantic model representing an incoming expense report."""

    amount: float = Field(..., description="Expense amount in USD")
    submitter: str = Field(..., description="Name or ID of submitter")
    category: str = Field(..., description="Category of expense, e.g., Meals, Travel")
    description: str = Field(..., description="Detailed description of expense")
    date: str = Field(..., description="Date of expense in YYYY-MM-DD format")
    redactions: list[str] = Field(
        default_factory=list, description="Categories of PII redacted from description"
    )


class RiskAssessment(BaseModel):
    """Pydantic model representing LLM or Security risk evaluation."""

    summary: str = Field(..., description="Summary of risk evaluation")
    risk_level: str = Field(..., description="LOW, MEDIUM, HIGH, or CRITICAL")
    risk_factors: list[str] = Field(
        default_factory=list, description="List of identified risk factors"
    )
    flagged_for_review: bool = Field(
        default=True, description="Whether human review is requested"
    )
    security_event: bool = Field(
        default=False, description="True if a security anomaly/injection was detected"
    )


class ExpenseDecision(BaseModel):
    """Final decision outcome for the expense report."""

    status: str = Field(..., description="APPROVED or REJECTED")
    decision_by: str = Field(
        ..., description="AUTO_APPROVE or HUMAN_APPROVER"
    )
    reason: str = Field(..., description="Explanation for decision")
    risk_assessment: RiskAssessment | None = Field(
        default=None, description="Associated risk assessment if applicable"
    )
    expense: ExpenseReport = Field(..., description="Final processed expense report")
