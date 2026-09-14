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

from expense_agent.config import (
    CREDIT_CARD_PATTERN,
    PROMPT_INJECTION_TERMS,
    SSN_PATTERN,
)


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """Scrubs sensitive PII (SSNs, Credit Cards) from text.

    Returns:
        tuple[str, list[str]]: (Sanitized text, list of redacted PII types)
    """
    redactions: list[str] = []
    sanitized_text = text

    if SSN_PATTERN.search(sanitized_text):
        sanitized_text = SSN_PATTERN.sub("[REDACTED_SSN]", sanitized_text)
        redactions.append("SSN")

    if CREDIT_CARD_PATTERN.search(sanitized_text):
        sanitized_text = CREDIT_CARD_PATTERN.sub(
            "[REDACTED_CREDIT_CARD]", sanitized_text
        )
        redactions.append("CREDIT_CARD")

    return sanitized_text, redactions


def detect_prompt_injection(text: str) -> bool:
    """Detects whether text contains prompt injection override patterns.

    Returns:
        bool: True if prompt injection pattern detected, False otherwise.
    """
    lower_text = text.lower()
    for term in PROMPT_INJECTION_TERMS:
        if term in lower_text:
            return True
    return False
