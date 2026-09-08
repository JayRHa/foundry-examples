"""Chat-UI mit Streamlit - der schnellste Weg zu einem teilbaren Prototyp.

    streamlit run 05_apps/streamlit_chat.py

Zeigt drei Dinge, die in Streamlit-Demos meist fehlen:
  - Der Agent wird gecacht (@st.cache_resource), nicht bei jedem Rerun neu
    angelegt. Streamlit fuehrt das Skript bei JEDER Interaktion komplett neu aus.
  - Der Thread liegt in st.session_state, ist also pro Browser-Sitzung stabil.
  - Streaming ueber einen Generator an st.write_stream - kein Warten auf die
    komplette Antwort.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import streamlit as st

from common import get_agents_client, settings

AGENT_NAME = "foundry-demo-streamlit"

st.set_page_config(page_title="Foundry Chat", page_icon="*", layout="centered")


@st.cache_resource(show_spinner="Agent wird vorbereitet ...")
def get_agent(instructions: str, model: str) -> str:
    """Einmal pro Prozess (bzw. pro Parameterkombination) ausgefuehrt."""
    agents = get_agents_client()
    existing = next((a for a in agents.list_agents() if a.name == AGENT_NAME), None)
    if existing:
        agents.update_agent(agent_id=existing.id, model=model, instructions=instructions)
        return existing.id
    return agents.create_agent(model=model, name=AGENT_NAME, instructions=instructions).id


with st.sidebar:
    st.header("Konfiguration")
    # Agent-Modell, nicht das Chat-Modell: das Agent Service akzeptiert die
    # neuesten Modelle noch nicht (siehe common/config.py).
    model = st.text_input("Agent-Deployment", settings.agent_model_deployment)
    instructions = st.text_area(
        "Instructions",
        "Du bist ein hilfsbereiter Assistent fuer ein internes Team. "
        "Antworte auf Deutsch, kurz und konkret.",
        height=140,
    )
    if st.button("Neues Gespraech", use_container_width=True):
        st.session_state.pop("thread_id", None)
        st.session_state.messages = []
        st.rerun()
    st.caption(f"Thread: `{st.session_state.get('thread_id', '-')}`")

agents = get_agents_client()
agent_id = get_agent(instructions, model)

if "thread_id" not in st.session_state:
    st.session_state.thread_id = agents.threads.create().id
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("Foundry Chat")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Frage stellen ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    agents.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt)

    def token_stream():
        with agents.runs.stream(
            thread_id=st.session_state.thread_id, agent_id=agent_id
        ) as stream:
            for event_type, event_data, _ in stream:
                if event_type != "thread.message.delta":
                    continue
                for part in event_data.delta.content or []:
                    if getattr(part, "text", None):
                        yield part.text.value

    with st.chat_message("assistant"):
        reply = st.write_stream(token_stream())

    st.session_state.messages.append({"role": "assistant", "content": reply})
