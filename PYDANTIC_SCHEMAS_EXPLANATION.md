# Pydantic Schemas Analysis & Architecture

## 1. Executive Summary

This document provides a comprehensive audit and architectural overview of all **Pydantic** (`pydantic.BaseModel`) schemas used throughout the `adk_ambient_expense_agent` repository. 

Across the agent codebase, **5 distinct Pydantic schemas** were identified. Pydantic serves four primary architectural purposes in this project:
1. **LLM Structured Output Constraints**: Guaranteing JSON schema adherence when Gemini models perform risk assessment during workflow execution and LLM-as-a-judge quality evaluations.
2. **Workflow Event Payload Validation & Data Transfer**: Modeling, parsing, and validating domain objects (expense claims, risk evaluations, and approval decisions) exchanged across Google ADK workflow nodes (`FunctionNode` and `LlmAgent`).
3. **Agent State & Memory Management**: Serializing and storing transient transaction data into the ADK context state (`ctx.state`) and human-in-the-loop (`RequestInput`) resumption payloads.
4. **API Endpoint Telemetry & Payload Schemas**: Validating incoming REST payloads for feedback collection endpoints in FastAPI.

---

## 2. Inventory & Categorization

The discovered Pydantic models are categorized below based on their primary architectural role in the application:

### Tool & Function Signatures
*No direct standalone Pydantic models are used for tool parameter definitions.* (The agent tools defined in [`app/agent.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/app/agent.py#L25-L56) utilize standard Python type hints (`query: str`), which ADK inspects automatically to construct tool parameters).

### Structured Outputs & Response Constraints
- **[`RiskAssessment`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L32-L45)**: Used as `output_schema` for the `review_risk` `LlmAgent` node in [`expense_agent/agent.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/agent.py#L186-L195) to enforce structured JSON output from Gemini.
- **[`_Verdict`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/tests/eval/response_quality.py#L8-L10)**: Used as `response_schema` in the `google.genai` SDK `GenerateContentConfig` to enforce JSON schema responses during LLM-as-a-judge evaluation in [`tests/eval/response_quality.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/tests/eval/response_quality.py#L34-L42).

### Agent State & Memory Management
- **[`ExpenseReport`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L19-L29)**: Represents raw and sanitized expense claims. Parsed in `parse_expense_event`, stored in `ctx.state["expense"]`, modified in `security_checkpoint`, and passed across workflow nodes.
- **[`ExpenseDecision`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L48-L59)**: Encapsulates the final decision outcome (`APPROVED` / `REJECTED`), decision source (`AUTO_APPROVE` / `HUMAN_APPROVER`), justification, and embedded [`RiskAssessment`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L32-L45) & [`ExpenseReport`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L19-L29) objects.

### Configuration & Settings
- **[`Feedback`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/app/app_utils/typing.py#L26-L34)**: Serves as the payload and logging schema for collecting user feedback and system telemetry at the `/feedback` FastAPI endpoint in [`app/fast_api_app.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/app/fast_api_app.py#L80-L91).

---

## 3. Detailed Code Walkthrough

### 3.1 [`ExpenseReport`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L19-L29)

**File Location**: [`expense_agent/models.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L19-L29)

```python
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
```

- **Role & Execution Flow**:
  - Serves as the central domain model for incoming financial claims.
  - Instantiated in [`parse_expense_event()`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/agent.py#L45-L114) from incoming JSON or decoded Google Cloud Pub/Sub payloads.
  - Evaluated against business rules (e.g. amount threshold `AUTO_APPROVE_THRESHOLD = $100`).
  - Updated in [`security_checkpoint()`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/agent.py#L139-L182) to scrub PII (replacing SSNs/Credit Cards in `description` and adding tags to `redactions`).
  - Stored in ADK context state (`ctx.state["expense"]`) and included in the final [`ExpenseDecision`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L48-L59).
- **Field Description Audit**:
  - `amount`: Includes clear `description="Expense amount in USD"`, but lacks lower/upper numeric validation bounds (`gt=0`).
  - `submitter`: Clear `description="Name or ID of submitter"`. Lacks string length constraints (`min_length=1`).
  - `category`: Has `description="Category of expense, e.g., Meals, Travel"`. Uses unconstrained `str` rather than an `Enum` or `Literal`.
  - `description`: Well-described. Modifiable by security sanitization routines.
  - `date`: Has `description="Date of expense in YYYY-MM-DD format"`. Uses primitive `str` without date regex validation or `datetime.date` typing.
  - `redactions`: Well-described with `default_factory=list`.

---

### 3.2 [`RiskAssessment`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L32-L45)

**File Location**: [`expense_agent/models.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L32-L45)

```python
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
```

- **Role & Execution Flow**:
  - Passed directly as `output_schema=RiskAssessment` to the `review_risk` `LlmAgent` in [`expense_agent/agent.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/agent.py#L186-L195).
  - The ADK framework translates this schema into a JSON Schema for Gemini's structured output generation (`response_mime_type="application/json"`), ensuring the LLM yields strictly structured risk evaluations.
  - Programmatically instantiated in [`security_checkpoint()`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/agent.py#L158-L164) when prompt injection is detected (`security_event=True`, `risk_level="HIGH"`), bypassing the LLM reviewer straight to human review.
  - Consumed by [`human_review()`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/agent.py#L198-L293) node to present risk context to the reviewer.
- **Field Description Audit**:
  - `summary`: Has `Field(..., description="Summary of risk evaluation")`. Effective micro-prompt.
  - `risk_level`: Has `description="LOW, MEDIUM, HIGH, or CRITICAL"`. Uses generic `str` instead of `Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]` or an `Enum`.
  - `risk_factors`: Has clear `description="List of identified risk factors"`.
  - `flagged_for_review`: Has clear `description` and appropriate default (`default=True`).
  - `security_event`: Has clear `description` and appropriate default (`default=False`).

---

### 3.3 [`ExpenseDecision`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L48-L59)

**File Location**: [`expense_agent/models.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L48-L59)

```python
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
```

- **Role & Execution Flow**:
  - Serves as the ultimate outcome contract generated by the workflow.
  - Produced in [`auto_approve()`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/agent.py#L117-L136) for low-value claims (`decision_by="AUTO_APPROVE"`).
  - Produced in [`human_review()`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/agent.py#L274-L280) following human-in-the-loop approval or rejection (`decision_by="HUMAN_APPROVER"`).
  - Dumped to JSON via `decision.model_dump()` and returned in event streams to Pub/Sub and web clients.
- **Field Description Audit**:
  - `status`: Has `description="APPROVED or REJECTED"`. Weak typing (`str` instead of `Literal["APPROVED", "REJECTED"]`).
  - `decision_by`: Has `description="AUTO_APPROVE or HUMAN_APPROVER"`. Weak typing (`str` instead of `Literal["AUTO_APPROVE", "HUMAN_APPROVER"]`).
  - `reason`: Has clear `description="Explanation for decision"`.
  - `risk_assessment`: Well-typed optional nested model (`RiskAssessment | None`).
  - `expense`: Well-typed nested model (`ExpenseReport`).

---

### 3.4 [`Feedback`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/app/app_utils/typing.py#L26-L34)

**File Location**: [`app/app_utils/typing.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/app/app_utils/typing.py#L26-L34)

```python
class Feedback(BaseModel):
    """Represents feedback for a conversation."""

    score: int | float
    text: str | None = ""
    log_type: Literal["feedback"] = "feedback"
    service_name: Literal["adk-ambient-expense-agent"] = "adk-ambient-expense-agent"
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
```

- **Role & Execution Flow**:
  - Used in [`app/fast_api_app.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/app/fast_api_app.py#L80-L91) as the Pydantic request body type for `@app.post("/feedback")`.
  - Deserializes incoming user feedback JSON payloads, assigns default UUIDs for missing `user_id` or `session_id` fields, and logs structured data to Google Cloud Logging via `logger.log_struct(feedback.model_dump(), severity="INFO")`.
- **Field Description Audit**:
  - `score`: **Missing `Field(description=...)`** and validation bounds (`ge=1, le=5`). Allows any float or integer value.
  - `text`: **Missing `Field(description=...)`**. Default value `""` is clear.
  - `log_type` & `service_name`: Excellent use of `Literal` tags for log categorization.
  - `user_id` & `session_id`: Effective use of `default_factory` with UUID generation, but lack `description`.

---

### 3.5 [`_Verdict`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/tests/eval/response_quality.py#L8-L10)

**File Location**: [`tests/eval/response_quality.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/tests/eval/response_quality.py#L8-L10)

```python
class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str
```

- **Role & Execution Flow**:
  - Acts as the structured output schema for the LLM-as-a-judge evaluation metric `custom_response_quality` in [`tests/eval/response_quality.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/tests/eval/response_quality.py#L34-L42).
  - Passed to `google.genai` SDK `types.GenerateContentConfig(response_mime_type="application/json", response_schema=_Verdict)`.
  - Ensures Gemini returns valid JSON containing an integer score and text explanation when grading agent response traces during `agents-cli eval grade`.
- **Field Description Audit**:
  - `score`: **Missing `Field(description=...)`** and bounds validation (`ge=1, le=5`). The inline comment `# 1-5` is ignored by the OpenAPI / JSON Schema generator.
  - `explanation`: **Missing `Field(description=...)`**.

---

## 4. Summary Matrix

| File Path | Schema / Class Name | Category | Primary Role in Workflow |
| :--- | :--- | :--- | :--- |
| [`expense_agent/models.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L19) | [`ExpenseReport`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L19-L29) | Agent State & Memory Management | Primary data object representing raw and PII-redacted expense submissions. |
| [`expense_agent/models.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L32) | [`RiskAssessment`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L32-L45) | Structured Outputs & Response Constraints | Constrains LLM output schema for `review_risk` node and represents security risk flags. |
| [`expense_agent/models.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L48) | [`ExpenseDecision`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L48-L59) | Agent State & Memory Management | Encapsulates final approval/rejection outcomes, reasons, and embedded risk reports. |
| [`app/app_utils/typing.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/app/app_utils/typing.py#L26) | [`Feedback`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/app/app_utils/typing.py#L26-L34) | Configuration & Settings | Request body validation model for `/feedback` API telemetry logging. |
| [`tests/eval/response_quality.py`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/tests/eval/response_quality.py#L8) | [`_Verdict`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/tests/eval/response_quality.py#L8-L10) | Structured Outputs & Response Constraints | Structured output target for LLM-as-a-judge evaluation scoring in eval runs. |

---

## 5. Recommended Refactoring & Improvements

### 5.1 Enforce Strict Enumerations for LLM & State Fields
Currently, string fields like `risk_level`, `status`, `decision_by`, and `category` use generic `str` types with descriptions suggesting fixed options. Replacing these with `Literal` types or Python `Enum` classes significantly improves LLM generation adherence and static typing safety:

```python
from typing import Literal

# Refactored RiskAssessment
class RiskAssessment(BaseModel):
    summary: str = Field(..., description="Summary of risk evaluation")
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        ..., description="Evaluated risk severity level"
    )
    risk_factors: list[str] = Field(
        default_factory=list, description="List of identified policy or security risk factors"
    )
    flagged_for_review: bool = Field(
        default=True, description="Whether human manager review is required"
    )
    security_event: bool = Field(
        default=False, description="True if a security anomaly or prompt injection was detected"
    )

# Refactored ExpenseDecision
class ExpenseDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"] = Field(..., description="Final approval status")
    decision_by: Literal["AUTO_APPROVE", "HUMAN_APPROVER"] = Field(
        ..., description="Mechanism that rendered the final decision"
    )
    reason: str = Field(..., description="Detailed explanation for the decision")
    risk_assessment: RiskAssessment | None = Field(default=None, description="Associated risk assessment")
    expense: ExpenseReport = Field(..., description="Final processed expense report")
```

### 5.2 Add Numerical Bounds and Format Validation
- **`ExpenseReport.amount`**: Add `gt=0` to enforce positive numerical values: `amount: float = Field(..., gt=0, description="Expense amount in USD")`.
- **`ExpenseReport.date`**: Enforce ISO 8601 date formatting using regex validation: `date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date of expense in YYYY-MM-DD format")`.
- **`Feedback.score` & `_Verdict.score`**: Enforce numeric boundaries `ge=1, le=5` to prevent out-of-bound evaluation ratings:
  ```python
  class _Verdict(BaseModel):
      score: int = Field(..., ge=1, le=5, description="Evaluation score from 1 (poor) to 5 (excellent)")
      explanation: str = Field(..., description="Detailed justification for the score")
  ```

### 5.3 Enhance Micro-Prompting in LLM-Facing Schemas
When passing Pydantic schemas as `output_schema` to ADK's `LlmAgent` or Gemini's `response_schema`, the field descriptions directly become micro-prompts for the LLM. 
- In [`_Verdict`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/tests/eval/response_quality.py#L8-L10), field descriptions are currently omitted. Adding explicit `Field(description=...)` metadata guides the LLM judge on how to structure its output and reasoning.
- In [`ExpenseReport`](file:///Users/ShahimaIA2/Desktop/adk_ambient_expense_agent/expense_agent/models.py#L19-L29), adding category examples or standard tags assists LLMs when extracting expense objects from unstructured text.
