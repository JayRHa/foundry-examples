.PHONY: install install-af check basics tools agents rag eval trace api ui cli clean

install:
	python3.11 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt
	@echo "Fertig. Aktivieren mit: source .venv/bin/activate"

install-af:                ## optional: Microsoft Agent Framework (08_agent_framework/)
	.venv/bin/pip install --pre -r requirements-agent-framework.txt

check:                     ## Verbindung und Projektinhalt pruefen - immer zuerst
	.venv/bin/python 09_ops/01_inspect_project.py

basics:
	@for f in 01_basics/*.py; do echo "== $$f"; .venv/bin/python $$f || exit 1; done

tools:
	@for f in 02_tools/*.py; do echo "== $$f"; .venv/bin/python $$f || exit 1; done

agents:
	@for f in 03_agents/*.py; do echo "== $$f"; .venv/bin/python $$f || exit 1; done

rag:
	.venv/bin/python 04_rag/01_build_index.py
	.venv/bin/python 04_rag/02_hybrid_search.py
	.venv/bin/python 04_rag/03_agent_search_tool.py

eval:
	.venv/bin/python 06_evaluation/02_batch_evaluate.py v1
	.venv/bin/python 06_evaluation/02_batch_evaluate.py v2

trace:
	.venv/bin/python 07_observability/01_tracing_console.py

api:                       ## PORT=8077 make api, falls 8000 belegt ist
	.venv/bin/python 05_apps/fastapi_chat_api.py

ui:
	.venv/bin/streamlit run 05_apps/streamlit_chat.py

cli:
	.venv/bin/python 05_apps/cli_agent.py

clean:
	rm -rf 03_agents/outputs 06_evaluation/outputs
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
