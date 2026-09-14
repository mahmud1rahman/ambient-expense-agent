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

from fastapi import Request
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import InMemoryRunner
from google.genai import types
import uvicorn

from expense_agent.agent import app as root_adk_app

# Standard Python console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("expense_agent.server")

# FastAPI App with Dev UI enabled
web_service = get_fast_api_app(agents_dir=".", web=True)

# Runner for processing workflow events
runner = InMemoryRunner(app=root_adk_app)


def normalize_subscription(subscription_path: str) -> str:
    """Normalizes fully-qualified Pub/Sub subscription path to a short name.

    Example:
        'projects/my-gcp-project/subscriptions/test-sub' -> 'test-sub'
    """
    if not subscription_path:
        return "ambient-sub"
    return subscription_path.split("/")[-1]


@web_service.post("/")
@web_service.post("/pubsub")
@web_service.post("/apps/expense_agent/pubsub")
@web_service.post("/apps/expense_agent/trigger/pubsub")
async def handle_pubsub_push(request: Request) -> dict[str, Any]:
    """HTTP POST push endpoint for Pub/Sub triggers."""
    body = await request.json()
    logger.info("Received ambient Pub/Sub trigger event")

    # Extract & normalize subscription path
    raw_sub = body.get("subscription", "")
    short_sub_name = normalize_subscription(raw_sub)
    user_id = short_sub_name
    logger.info(f"Normalized subscription path '{raw_sub}' -> userId '{user_id}'")

    # Extract Pub/Sub message data
    message = body.get("message", {})
    message_id = message.get("messageId", "evt")

    # Create readable session ID using normalized subscription name
    session_id = f"{short_sub_name}-{message_id}"

    # Create or retrieve session mapped to user_id (subscription short name)
    try:
        session = await runner.session_service.create_session(
            app_name=root_adk_app.name,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        session = await runner.session_service.get_session(
            app_name=root_adk_app.name,
            user_id=user_id,
            session_id=session_id,
        )

    # Format input payload for the workflow
    if "data" in message:
        payload_data = {"data": message["data"]}
    else:
        payload_data = body

    payload_str = json.dumps(payload_data)

    results = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part.from_text(text=payload_str)]
        ),
    ):
        if event.output is not None:
            results.append(event.output)

    logger.info(
        f"Workflow executed for session '{session.id}' (userId '{user_id}') with {len(results)} outputs."
    )

    return {
        "status": "PROCESSED",
        "subscription": short_sub_name,
        "user_id": user_id,
        "session_id": session.id,
        "results": results,
    }


def start_server(host: str = "127.0.0.1", port: int = 8080):
    """Starts the web server with Dev UI on port 8080."""
    logger.info(f"Starting Ambient Expense Approval Service with Dev UI on {host}:{port}")
    uvicorn.run(web_service, host=host, port=port)


if __name__ == "__main__":
    start_server()
