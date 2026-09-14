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

import os
import re
from dotenv import load_dotenv

# Load local .env file
load_dotenv()

# If GEMINI_API_KEY is provided and GOOGLE_GENAI_USE_VERTEXAI is not explicitly set to true, default to AI Studio API Key mode
if os.getenv("GEMINI_API_KEY") and os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() != "true":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

AUTO_APPROVE_THRESHOLD: float = float(os.getenv("AUTO_APPROVE_THRESHOLD", "100.0"))
MODEL_NAME: str = os.getenv("MODEL_NAME", "gemini-3.1-flash-lite")

# PII Matching Regex Patterns
SSN_PATTERN = re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b")
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

# Prompt Injection Defense Keywords & Phrases
PROMPT_INJECTION_TERMS: list[str] = [
    "ignore previous instructions",
    "ignore all instructions",
    "override system prompt",
    "system:",
    "bypass rules",
    "auto approve",
    "auto-approve",
    "say approved",
    "do not review",
    "disregard safety",
    "forget previous rules",
]
