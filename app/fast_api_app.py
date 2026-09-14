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

import contextlib
import os
from collections.abc import AsyncIterator

import google.auth
from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.cloud import logging as google_cloud_logging

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

load_dotenv()
setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=False,
    lifespan=lifespan,
)
app.title = "adk-ambient-expense-agent"
app.description = "API for interacting with the Agent adk-ambient-expense-agent"


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


class ActionRequest(BaseModel):
    approved: bool
    interrupt_id: str


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the minimalistic dashboard HTML."""
    template_path = os.path.join(AGENT_DIR, "app", "templates", "dashboard.html")
    try:
        with open(template_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="Dashboard HTML not found.", status_code=404)


@app.get("/api/pending")
async def get_pending_approvals():
    """Returns mock pending approvals for the dashboard."""
    return [
        {
            "session_id": "ses_mock12345678",
            "amount": 250.00,
            "claimant": "Alice Smith",
            "purpose": "Client dinner at high-end restaurant",
            "message": "Amount exceeds auto-approve threshold ($100.00).",
            "interrupt_id": "int_mock123"
        },
        {
            "session_id": "ses_mock87654321",
            "amount": 1200.00,
            "claimant": "Bob Jones",
            "purpose": "Flight to conference in Tokyo",
            "message": "Requires VP approval for international travel.",
            "interrupt_id": "int_mock456"
        }
    ]


@app.post("/api/action/{session_id}")
async def handle_approval_action(session_id: str, action: ActionRequest):
    """Handles mock approval actions from the dashboard."""
    status = "APPROVED" if action.approved else "REJECTED"
    return {
        "status": status,
        "session_id": session_id,
        "review_summary": f"Mock review executed. User requested {status.lower()} via dashboard.",
        "decision": status
    }


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
