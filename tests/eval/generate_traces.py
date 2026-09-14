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

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from google.adk.runners import InMemoryRunner
from google.genai import types

from expense_agent.agent import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generate_traces")


def parse_event_output(event: Any) -> list[dict[str, Any]]:
    """Helper to convert event outputs into part dictionaries."""
    parts = []
    if event.output is not None:
        if isinstance(event.output, dict):
            parts.append({"text": json.dumps(event.output)})
        else:
            parts.append({"text": str(event.output)})
    return parts


async def process_eval_case(runner: InMemoryRunner, case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["eval_case_id"]
    prompt_text = case["prompt"]["parts"][0]["text"]
    user_id = f"eval-user-{case_id}"
    session_id = f"eval-session-{case_id}"

    logger.info(f"Running scenario '{case_id}'...")

    # Create isolated session
    session = await runner.session_service.create_session(
        app_name="app",
        user_id=user_id,
        session_id=session_id,
    )

    turns = []
    turn_counter = 0

    # Turn 0: User prompt -> workflow initial output
    events_t0 = [
        {
            "author": "user",
            "content": {
                "role": "user",
                "parts": [{"text": prompt_text}],
            },
        }
    ]

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part.from_text(text=prompt_text)]
        ),
    ):
        parts = parse_event_output(event)
        if parts:
            events_t0.append({
                "author": "model",
                "content": {
                    "role": "model",
                    "parts": parts,
                },
            })

    turns.append({
        "turn_index": turn_counter,
        "events": events_t0,
    })
    turn_counter += 1

    # Check updated session state
    updated_session = await runner.session_service.get_session(
        app_name="app",
        user_id=user_id,
        session_id=session.id,
    )
    state = updated_session.state or {}
    risk_assessment = state.get("risk_assessment") or {}

    # Turn 1: HITL decision if human review was requested
    if risk_assessment:
        if risk_assessment.get("security_event") or risk_assessment.get("risk_level") == "HIGH":
            decision = "reject"
        else:
            decision = "approve"

        logger.info(f"Intercepted HITL decision for '{case_id}': '{decision}'")

        events_t1 = [
            {
                "author": "user",
                "content": {
                    "role": "user",
                    "parts": [{"text": decision}],
                },
            }
        ]

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=decision)]
            ),
        ):
            parts = parse_event_output(event)
            if parts:
                events_t1.append({
                    "author": "model",
                    "content": {
                        "role": "model",
                        "parts": parts,
                    },
                })

        turns.append({
            "turn_index": turn_counter,
            "events": events_t1,
        })

    # Extract last model response content for single-turn responses field
    last_response_parts = []
    for t in reversed(turns):
        for ev in reversed(t["events"]):
            if ev["author"] == "model" and ev["content"]["parts"]:
                last_response_parts = ev["content"]["parts"]
                break
        if last_response_parts:
            break

    if not last_response_parts:
        last_response_parts = [{"text": "Processed expense request."}]

    return {
        "eval_case_id": case_id,
        "prompt": case["prompt"],
        "responses": [
            {
                "response": {
                    "role": "model",
                    "parts": last_response_parts,
                }
            }
        ],
        "agent_data": {
            "turns": turns,
        },
    }


async def main():
    dataset_path = Path("tests/eval/datasets/basic-dataset.json")
    output_path = Path("artifacts/traces/generated_traces.json")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    runner = InMemoryRunner(app=app)
    traces = []

    for case in dataset.get("eval_cases", []):
        trace_case = await process_eval_case(runner, case)
        traces.append(trace_case)

    trace_file_content = {"eval_cases": traces}

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(trace_file_content, f, indent=2)

    logger.info(f"Successfully generated {len(traces)} traces at '{output_path}'")


if __name__ == "__main__":
    asyncio.run(main())
