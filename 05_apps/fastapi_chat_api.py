"""Chat-API mit FastAPI und Server-Sent Events auf Basis des Agent Service.

    python 05_apps/fastapi_chat_api.py          # Port 8000, oder PORT=8077 setzen
    # oder: uvicorn 05_apps.fastapi_chat_api:app --reload --app-dir .

    curl -N -X POST localhost:8000/chat/stream \
         -H 'content-type: application/json' \
         -d '{"conversation_id":"demo","message":"Was kann das Agent Service?"}'

Die Referenzarchitektur fuer eine Chat-App auf Foundry:

  - Der Agent wird EINMAL beim Start sichergestellt, nicht pro Request.
  - Die Konversation lebt als Thread im Dienst; die App speichert nur die
    Zuordnung conversation_id -> thread_id (hier in-memory, real in Redis/DB).
  - Gestreamt wird ueber SSE: jedes Event hat einen Typ, damit das Frontend
    "sucht gerade" von "Antworttext" unterscheiden kann.
  - Der Client sieht nie Endpoint, Deployment oder Token.
"""

import json
import os
import pathlib
import sys
from contextlib import asynccontextmanager

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from common import get_agents_client, settings

AGENT_NAME = "foundry-demo-api"
INSTRUCTIONS = (
    "Du bist der Assistent einer internen Web-App. Antworte auf Deutsch, "
    "kurz und konkret. Wenn du etwas nicht weisst, sage es."
)

# In Produktion: Redis/Postgres. Ein Dict ueberlebt keinen Neustart und kein Scale-out.
THREADS: dict[str, str] = {}
STATE: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    agents = get_agents_client()
    existing = next((a for a in agents.list_agents() if a.name == AGENT_NAME), None)
    agent = existing or agents.create_agent(
        model=settings.agent_model_deployment, name=AGENT_NAME, instructions=INSTRUCTIONS
    )
    STATE["agent_id"] = agent.id
    print(f"[startup] Agent {agent.id} ({'wiederverwendet' if existing else 'neu'})")
    yield
    # Agent bewusst NICHT loeschen: er ist Konfiguration, kein Request-Artefakt.


app = FastAPI(title="Foundry Chat API", lifespan=lifespan)


class ChatRequest(BaseModel):
    conversation_id: str = Field(description="Stabile ID pro Nutzer/Gespraech")
    message: str


def thread_for(conversation_id: str) -> str:
    if conversation_id not in THREADS:
        THREADS[conversation_id] = get_agents_client().threads.create().id
    return THREADS[conversation_id]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    """Blockierende Variante - fuer Batch-Jobs und Tests."""
    agents = get_agents_client()
    thread_id = thread_for(request.conversation_id)

    agents.messages.create(thread_id=thread_id, role="user", content=request.message)
    run = agents.runs.create_and_process(thread_id=thread_id, agent_id=STATE["agent_id"])
    if run.status == "failed":
        raise HTTPException(status_code=502, detail=str(run.last_error))

    message = agents.messages.get_last_message_by_role(thread_id=thread_id, role="assistant")
    return {
        "conversation_id": request.conversation_id,
        "reply": message.text_messages[-1].text.value,
        "usage": run.usage.as_dict() if run.usage else None,
    }


@app.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """SSE-Variante - das, was eine UI tatsaechlich nutzt."""
    agents = get_agents_client()
    thread_id = thread_for(request.conversation_id)
    agents.messages.create(thread_id=thread_id, role="user", content=request.message)

    def events():
        yield sse("start", {"thread_id": thread_id})
        try:
            with agents.runs.stream(thread_id=thread_id, agent_id=STATE["agent_id"]) as stream:
                for event_type, event_data, _ in stream:
                    if event_type == "thread.message.delta":
                        text = "".join(
                            part.text.value
                            for part in (event_data.delta.content or [])
                            if getattr(part, "text", None)
                        )
                        if text:
                            yield sse("token", {"text": text})
                    elif event_type == "thread.run.step.created":
                        # Zwischenstand fuer die UI: "Agent nutzt ein Tool"
                        yield sse("step", {"type": getattr(event_data, "type", "")})
                    elif event_type == "thread.run.failed":
                        yield sse("error", {"detail": str(event_data.last_error)})
        except Exception as exc:
            yield sse("error", {"detail": f"{type(exc).__name__}: {exc}"})
        yield sse("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Minimale Testseite - reines EventSource-Handling, kein Framework."""
    return """<!doctype html><meta charset="utf-8"><title>Foundry Chat</title>
<style>body{font:15px/1.5 system-ui;max-width:44rem;margin:3rem auto;padding:0 1rem}
#out{white-space:pre-wrap;border:1px solid #ddd;border-radius:8px;padding:1rem;min-height:8rem}
input{width:100%;padding:.6rem;font:inherit;margin-top:1rem}</style>
<h1>Foundry Chat</h1><div id="out"></div>
<input id="q" placeholder="Frage eingeben und Enter" autofocus>
<script>
const out = document.getElementById('out'), q = document.getElementById('q');
q.addEventListener('keydown', async e => {
  if (e.key !== 'Enter' || !q.value.trim()) return;
  const message = q.value; q.value = ''; out.textContent += `\\n\\nDu: ${message}\\nAgent: `;
  const res = await fetch('/chat/stream', {method:'POST', headers:{'content-type':'application/json'},
    body: JSON.stringify({conversation_id:'browser', message})});
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for(;;) {
    const {value, done} = await reader.read(); if (done) break;
    buffer += value;
    const frames = buffer.split('\\n\\n'); buffer = frames.pop();
    for (const frame of frames) {
      const ev = /event: (.*)/.exec(frame)?.[1], data = /data: (.*)/.exec(frame)?.[1];
      if (ev === 'token') out.textContent += JSON.parse(data).text;
      if (ev === 'error') out.textContent += `\\n[Fehler] ${JSON.parse(data).detail}`;
    }
  }
});
</script>"""


if __name__ == "__main__":
    # Port ueberschreibbar: 8000 ist auf Entwicklerrechnern haeufig belegt
    # (Docker Desktop, OrbStack, andere Dev-Server).
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
