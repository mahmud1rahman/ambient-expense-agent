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
import logging
from typing import Any

from fastapi import FastAPI, Request
from google.adk.runners import InMemoryRunner
from google.genai import types

from expense_agent.agent import app

logger = logging.getLogger("expense_agent.pubsub")

# FastAPI extension app mounted automatically by ADK web server
fast_api_app = FastAPI(title="Ambient PubSub Extension")

# Runner for processing Pub/Sub events
runner = InMemoryRunner(app=app)


def normalize_subscription(subscription_path: str) -> str:
    """Normalizes fully-qualified Pub/Sub subscription path to a short name.

    Example:
        'projects/my-gcp-project/subscriptions/expense-approval-sub' -> 'expense-approval-sub'
    """
    if not subscription_path:
        return "ambient-sub"
    return subscription_path.split("/")[-1]


@fast_api_app.post("/pubsub")
@fast_api_app.post("/events")
async def handle_pubsub_push(request: Request) -> dict[str, Any]:
    """HTTP POST push endpoint for Pub/Sub triggers."""
    body = await request.json()
    logger.info("Received ambient Pub/Sub trigger event")

    raw_sub = body.get("subscription", "")
    short_sub_name = normalize_subscription(raw_sub)

    message = body.get("message", {})
    message_id = message.get("messageId", "evt")
    session_id = f"{short_sub_name}-{message_id}"

    try:
        session = await runner.session_service.create_session(
            app_name="app",
            user_id=f"user-{short_sub_name}",
            session_id=session_id,
        )
    except Exception:
        session = await runner.session_service.get_session(
            app_name="app",
            user_id=f"user-{short_sub_name}",
            session_id=session_id,
        )

    if "data" in message:
        payload_data = {"data": message["data"]}
    else:
        payload_data = body

    payload_str = json.dumps(payload_data)

    results = []
    async for event in runner.run_async(
        user_id=f"user-{short_sub_name}",
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part.from_text(text=payload_str)]
        ),
    ):
        if event.output is not None:
            results.append(event.output)

    return {
        "status": "PROCESSED",
        "subscription": short_sub_name,
        "session_id": session.id,
        "results": results,
    }
