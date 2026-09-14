# Project Architecture and Tech Stack

This document outlines the architecture, technology stack, and deployment processes for the **adk-ambient-expense-agent** project.

## Overview
The `adk-ambient-expense-agent` is a ReAct-based AI agent built using the **Google Agent Development Kit (ADK)** and exposed via a **FastAPI** backend server. It relies on the Google Gemini model for intelligence and utilizes the **A2A Protocol** for agent-to-agent interoperability.

## Technology Stack

### Core Technologies
- **Language**: Python 3.11+
- **Agent Framework**: Google ADK (`google-adk[gcp]>=2.0.0`)
- **Web Framework**: FastAPI (`fastapi>=0.110.0`, `uvicorn>=0.28.0`)
- **AI Model**: Google Gemini (`gemini-flash-latest` configured via `google.adk.models.Gemini`)
- **Interoperability**: A2A Protocol (`a2a-sdk[http-server]~=0.3.22`)

### Development & Build Tools
- **Package Manager**: `uv`
- **CLI Tooling**: `agents-cli` (v1.1.0)
- **Testing**: `pytest`, `pytest-asyncio`
- **Linting & Type Checking**: `ruff`, `ty`, `codespell`

### Observability & Telemetry
- **OpenTelemetry**: `opentelemetry-instrumentation-google-genai`
- **Cloud Logging**: `google-cloud-logging>=3.12.0`
- **Tracing/Analytics**: Google Cloud Trace, BigQuery (Built-in ADK telemetry)

## Architecture

The project follows a standard structured layout initialized by the `agents-cli`:

1.  **Agent Logic (`app/agent.py`)**: Defines the `root_agent` using ADK's `Agent` class. It employs the ReAct paradigm and provides tools (e.g., `get_weather`, `get_current_time`) for the Gemini model to interact with external logic.
2.  **API Layer (`app/fast_api_app.py`)**: Wraps the ADK agent into a RESTful FastAPI web application. It integrates session state management, artifact services, A2A routes, and logging mechanisms.
3.  **State Management**: By default, sessions and tasks are managed locally in memory (e.g., `InMemoryTaskStore`), which can be configured for production stores via ADK Runner injection.

## Deployments (ADK to GCP)

Deployment to Google Cloud Platform (GCP) is fully managed through the `agents-cli` tool.

### 1. Manual Deployment
For rapid iteration, the agent can be deployed directly to development or staging environments on GCP.
```bash
gcloud config set project <your-project-id>
agents-cli deploy
```

### 2. Infrastructure as Code & CI/CD
For production-grade deployments, the project can be scaffolded to include Terraform configurations and CI/CD pipelines (e.g., GitHub Actions or Cloud Build).
- **Add CI/CD pipelines and Terraform**:
  ```bash
  agents-cli scaffold enhance
  ```
- **Deploy Infrastructure + Pipeline**:
  ```bash
  agents-cli infra cicd
  ```

### Target GCP Services
Depending on the specific `agents-cli` infrastructure setup, the agent is typically deployed to:
- **Cloud Run**: For hosting the FastAPI server container.
- **Cloud Logging / Trace**: For built-in telemetry observability.
- **Vertex AI / Gemini API**: For underlying model inference execution.

## Testing and Evaluation
- **Unit/Integration Tests**: Run via `uv run pytest tests/unit tests/integration`.
- **Agent Evaluation**: Handled by `agents-cli eval` suite, using multi-turn eval datasets and LLM-as-a-judge scoring to ensure prompt and tool usage stability before deployment.
