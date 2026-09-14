.PHONY: install serve playground test run generate-traces grade

install:
	uv sync

serve:
	uv run python -m expense_agent.server

playground:
	uvx --no-build google-agents-cli playground

test:
	uv run pytest tests/test_expense_agent.py

run:
	uvx --no-build google-agents-cli run '{"amount": 150.0, "submitter": "alice@company.com", "category": "software", "description": "IDE License", "date": "2026-06-06"}'

generate-traces:
	uv run python tests/eval/generate_traces.py

grade:
	uvx --no-build google-agents-cli eval grade --traces artifacts/traces/generated_traces.json --config tests/eval/eval_config.yaml
