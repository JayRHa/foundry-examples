# Azure AI Foundry - Beispielprojekt (Python)

> Deutsche Fassung. Die englische Version ist [README.md](README.md).

Ein Katalog lauffaehiger Beispiele: vom einfachen Modellaufruf ueber Tools,
Agents und RAG bis zu Evaluation, Tracing und den Dingen, die zwischen Prototyp
und Produktion liegen.

Jede Datei laeuft eigenstaendig, erklaert im Docstring **warum** etwas so gemacht
wird, und ist so kurz gehalten, dass man sie in einem Rutsch liest.

```bash
python 01_basics/01_chat_completion.py
```

> **Alle 37 Beispiele sind gegen ein echtes Foundry-Projekt ausgefuehrt worden**
> (Sweden Central, Python 3.11) - inklusive Azure AI Search, Grounding with Bing
> Search und Application Insights. Die Versionen in `requirements.txt` sind die
> getesteten, und die Kommentare im Code beschreiben Fehler, die dabei
> tatsaechlich aufgetreten sind - nicht solche, die theoretisch auftreten
> koennten.

---

## Setup

### 1. Was du in Azure brauchst

| | |
|---|---|
| Foundry-Ressource | `Microsoft.CognitiveServices/accounts`, Kind `AIServices`, mit **Managed Identity** und **`allowProjectManagement: true`** |
| Foundry-Projekt | Child-Resource der Ressource; liefert den Endpoint `https://<name>.services.ai.azure.com/api/projects/<projekt>` |
| Chat-Deployment | `gpt-5.6-sol` (der Deployment-Name ist frei waehlbar - er landet in `.env`) |
| Agent-Deployment | `gpt-4o` - siehe "Welches Modell wo" |
| Embedding-Deployment | `text-embedding-3-small`, nur fuer RAG |
| Rollen auf der Ressource | **Foundry User** (frueher "Azure AI User", Rollen-ID `53ca6127-db72-4b80-b1b0-d745d6d5456d`) und **Cognitive Services OpenAI User** |

Optional, jeweils als *Connection* im Projekt verknuepft:
Azure AI Search (RAG), Grounding with Bing Search, Application Insights (Tracing).
Was diese Connections brauchen, steht unten unter "Optionale Bausteine".

### 2. Lokal

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # Endpoint + Deployment-Namen eintragen
az login
```

Kein API-Key noetig: `DefaultAzureCredential` nimmt das Token aus `az login`,
in Azure die Managed Identity, in CI den Service Principal.

### 3. Pruefen

```bash
python 09_ops/01_inspect_project.py
```

Listet Deployments, Connections und Agents. Weicht hier etwas von `.env` ab,
scheitern die Beispiele genau daran.

---

## Welches Modell wo - und warum nicht ueberall dasselbe

Das Repo nutzt **`gpt-5.6-sol` ueberall, wo es geht**. Es geht an genau einer
Stelle nicht, und das ist keine Geschmacksfrage:

| Wo | Deployment | Grund |
|---|---|---|
| Chat Completions, Responses API, Tools, RAG-Antwort, Prompt-Templates, Evaluations-Judge, Agent Framework | **`gpt-5.6-sol`** | volle Unterstuetzung |
| Klassisches Agent Service (`03_agents/`, `04_rag/03`, `05_apps/`, `06_evaluation/03`, `07_observability/`) | **`gpt-4o`** | siehe unten |
| Embeddings | `text-embedding-3-small` | es gibt kein GPT-5-Embedding-Modell |
| `01_basics/06_model_catalog.py` (zweiter Aufruf) | `llama-3.3-70b` | der Sinn des Beispiels ist ein Nicht-OpenAI-Modell |

**Das klassische Agent Service ist die Bremse, nicht das Modell.** Dort scheitern
neue Modelle an zwei unabhaengigen Huerden:

*Huerde 1 - `top_p`.* Das Agent Service setzt bei jedem Run intern ein `top_p`.
Die neuesten Modelle lehnen den Parameter ab:

```
{'code': 'invalid_prompt', 'message': "Unsupported parameter: 'top_p' is not supported with this model."}
```

Das laesst sich nicht unterdruecken - weder ueber `create_agent(top_p=...)` noch
ueber `runs.create(top_p=...)`, und auch keine neuere API-Version hilft.

*Huerde 2 - Tool-Kompatibilitaet.* Auch die GPT-5-Modelle, die die erste Huerde
nehmen, unterstuetzen dort nur einen Teil der Tools. `gpt-5-mini` sagt es klar,
`gpt-5.4` quittiert dieselben Faelle mit einem nichtssagenden
`server_error: Sorry, something went wrong.`:

```
The model 'gpt-5-mini' cannot be used with the following tools: openapi.
This model only supports Responses API compatible tools.
```

Getestet, Agent Service:

| Modell | Run kommt durch | Code Interpreter / File Search / MCP | OpenAPI / Bing / Connected Agents / AI Search |
|---|---|---|---|
| `gpt-5.6-sol` | nein (`top_p`) | - | - |
| `gpt-5.5` | nein (`top_p`) | - | - |
| `gpt-5.4` | ja | ja | nein (`server_error`) |
| `gpt-5-mini` | ja (ohne `temperature`) | ja | nein (klare Meldung) |
| **`gpt-4o`** | **ja** | **ja** | **ja** |

Deshalb steht `AGENT_MODEL_DEPLOYMENT_NAME=gpt-4o`. Wer in seinem Projekt nur
Code Interpreter, File Search oder MCP nutzt, kann dort `gpt-5.4` eintragen.

**Die Konsequenz fuer neue Projekte:** Das klassische Agent Service ist die
Legacy-Oberflaeche. Fuer neue Modelle fuehrt der Weg ueber die Responses API
bzw. das Agent Framework (`08_agent_framework/`) - dort laeuft `gpt-5.6-sol`
inklusive Tools ohne Einschraenkung.

## Was sich mit der GPT-5-Familie im Code aendert

| Frueher | Jetzt | Sonst |
|---|---|---|
| `max_tokens=400` | `max_completion_tokens=4000` | `Unsupported parameter: 'max_tokens' ... Use 'max_completion_tokens' instead` |
| `temperature=0` | weglassen | `Unsupported value: 'temperature' does not support 0 ... Only the default (1)` |
| `top_p=0.9` | weglassen | `Unsupported parameter: 'top_p' is not supported with this model` |
| - | `reasoning_effort="none"\|"low"\|"medium"\|"high"` | der eigentliche Kostenregler, siehe `01_basics/08` |
| `"role": "system"` | `"role": "developer"` | beides funktioniert noch; `developer` ist die vorgesehene Form |

Zwei Folgen, die man leicht uebersieht:

- **`max_completion_tokens` deckt auch die unsichtbaren Reasoning-Tokens ab.**
  Zu knapp gesetzt kommt eine *leere* Antwort mit `finish_reason="length"`
  zurueck - bezahlt, aber ohne Ergebnis. Deshalb stehen hier ueberall grosszuegige
  Budgets (2000-8000) statt der frueheren 150-500.
- **`temperature=0` als Determinismus-Werkzeug faellt weg.** Reproduzierbarkeit
  holt man sich jetzt ueber Structured Outputs (`01_basics/03`), enge Schemas und
  praezise Prompts.

Zwei SDKs brauchen einen expliziten Schalter:

```python
# azure-ai-evaluation: ohne das Flag sendet der Judge intern max_tokens
GroundednessEvaluator(model_config=config, is_reasoning_model=True)

# azure-ai-inference: kennt max_completion_tokens nur als Durchreiche-Feld
client.complete(messages=..., model_extras={"max_completion_tokens": 3000})
```

---

## Der Katalog

### `01_basics/` - Modellaufrufe

| Datei | Thema |
|---|---|
| `01_chat_completion.py` | Der Grundaufruf, Client aus dem Projekt, Token-Zaehlung |
| `02_streaming.py` | Token-Streaming inkl. Usage am Ende (`stream_options`) |
| `03_structured_output.py` | Garantiert valides JSON gegen ein Pydantic-Schema |
| `04_vision_multimodal.py` | Bilder als base64-`data:`-URL, Kostenhebel `detail` |
| `05_embeddings.py` | Batching, gekuerzte Dimensionen, Aehnlichkeit |
| `06_model_catalog.py` | Llama/Mistral/Phi/Cohere mit derselben API - und wo die Parameter auseinandergehen (`06_model_catalog.py llama-3.3-70b`) |
| `07_responses_api.py` | Serverseitiger Gespraechszustand statt History im Request |
| `08_reasoning_model.py` | `reasoning_effort` im Vergleich (none/low/medium/high) mit Zeit und Reasoning-Tokens |

### `02_tools/` - Function Calling

| Datei | Thema |
|---|---|
| `01_function_calling.py` | Der Tool-Loop von Hand - einmal bauen lohnt sich |
| `02_tool_registry.py` | Schema aus Type Hints, parallele Ausfuehrung (4 Calls in 1s statt 4s) |
| `03_mcp_via_responses.py` | MCP-Server einbinden, Approval-Modi, Sicherheitshinweise |

### `03_agents/` - Azure AI Agent Service

| Datei | Thema |
|---|---|
| `01_hello_agent.py` | Agent / Thread / Run - das Grundmodell |
| `02_agent_function_tools.py` | Eigene Funktionen als Tools, Guards im Code statt im Prompt |
| `03_code_interpreter.py` | Datenanalyse in der Sandbox, erzeugte PNGs abholen |
| `04_file_search_rag.py` | RAG ohne eigene Pipeline (Vector Store), mit Zitaten |
| `05_streaming_events.py` | Event-Handler: sehen, was der Agent gerade tut |
| `06_bing_grounding.py` | Aktuelle Fakten mit Quellenpflicht |
| `07_connected_agents.py` | Multi-Agent: Orchestrator delegiert an Spezialisten |
| `08_openapi_tool.py` | Bestehende REST-API ohne Glue-Code anbinden (ruft echtes Open-Meteo) |
| `09_mcp_tool.py` | MCP im Agent Service inkl. Freigabe-Workflow |
| `10_lifecycle.py` | Agents und Threads ueber Prozessgrenzen hinweg (CLI) |

### `04_rag/` - Eigener Suchindex

| Datei | Thema |
|---|---|
| `01_build_index.py` | Chunking an Ueberschriften, Embeddings, HNSW + Semantic + **Vectorizer** |
| `02_hybrid_search.py` | BM25 + Vektor + Reranking, nummerierte Zitate mit Rueckabbildung |
| `03_agent_search_tool.py` | Derselbe Index als Agent-Tool |

### `05_apps/` - Anwendungen

| Datei | Thema |
|---|---|
| `fastapi_chat_api.py` | Chat-API mit SSE-Streaming, Thread-Mapping, Testseite (`PORT=8077 python ...`) |
| `streamlit_chat.py` | Prototyp-UI mit korrektem Caching und Session-State |
| `cli_agent.py` | Terminal-Assistent mit Dateizugriff und Pfad-Guard |

### `06_evaluation/` - Qualitaet messen

| Datei | Thema |
|---|---|
| `01_evaluators.py` | Groundedness/Relevance + eigener regelbasierter Evaluator |
| `02_batch_evaluate.py` | A/B zweier Prompt-Versionen, Upload ins Portal |
| `03_agent_evaluation.py` | Intent Resolution, Tool Call Accuracy, Task Adherence |

### `07_observability/` - Tracing

| Datei | Thema |
|---|---|
| `01_tracing_console.py` | OpenTelemetry-Spans lokal ansehen |
| `02_tracing_app_insights.py` | Traces in Azure Monitor + drei gegen echte Daten gepruefte KQL-Abfragen |

### `08_agent_framework/` - Microsoft Agent Framework (optional)

| Datei | Thema |
|---|---|
| `01_basics.py` | Agent als lokales Objekt, Tools als Python-Funktionen, Session, Streaming |
| `02_workflow.py` | Fester Ablauf als Graph statt freier Delegation |

Eigene Requirements-Datei, siehe `08_agent_framework/README.md`.

### `09_ops/` - Betrieb

| Datei | Thema |
|---|---|
| `01_inspect_project.py` | Inventar: Deployments, Connections, Agents |
| `02_prompt_templates.py` | Prompts als versionierte `.prompty`-Dateien |
| `03_production_hardening.py` | 429-Backoff mit `retry-after-ms`, Content Filter, Timeouts, Kosten |

---

## Welchen Weg nehme ich wofuer?

**Ein Modellaufruf, eigene Logik drumherum** -> `01_basics/` + `02_tools/`
Volle Kontrolle, kein Zustand im Dienst, am besten testbar. Der Default, solange
es reicht.

**Zustand, eingebaute Tools, wenig eigener Code** -> `03_agents/`
Threads, File Search, Code Interpreter, Bing, OpenAPI - alles serverseitig. Der
schnellste Weg zu einem Assistenten, dafuer weniger Kontrolle ueber Details.

**Portabel, komplexe Orchestrierung** -> `08_agent_framework/`
Wenn der Ablauf ein Graph mit Bedingungen und Checkpoints ist, oder wenn der
Modellanbieter austauschbar bleiben soll.

**RAG:** Erst `03_agents/04_file_search_rag.py` probieren. Reicht das nicht -
eigenes Chunking, Metadatenfilter, grosser Korpus - dann `04_rag/`.

---

## Die SDK-Fallen, die am meisten Zeit kosten

Alle sind hier tatsaechlich aufgetreten und an der jeweiligen Stelle im Code
kommentiert.

**1. `azure-ai-projects` 2.x ist ein Bruch gegenueber 1.x.**
`project.agents` ist in 2.x nicht mehr der klassische AgentsClient, sondern die
neue deklarative Agent-Version-API:

```
AttributeError: 'AgentsOperations' object has no attribute 'create_agent'
```

Loesung (in `common/clients.py`): den `AgentsClient` direkt aus dem eigenen
Paket `azure-ai-agents` bauen, nicht ueber das Projekt beziehen. Ebenso nimmt
`get_openai_client()` in 2.x kein `api_version` mehr -
`TypeError: OpenAI.__init__() got an unexpected keyword argument 'api_version'`.

**2. Der projektbezogene `/openai/v1` bedient keine Embeddings.**
`get_openai_client()` zeigt in 2.x auf
`{endpoint}/api/projects/{projekt}/openai/v1`. Chat und Responses funktionieren
dort, `/embeddings` antwortet mit einem nackten `404` ohne Erklaerung. Der
Endpoint der *Ressource* (`{endpoint}/openai/v1`) bedient beides -
`common/clients.py` setzt die `base_url` deshalb um.

**3. Tracing ohne `azure-core-tracing-opentelemetry` zeigt nur die eigenen Spans.**
Die Instrumentierung meldet Erfolg, aber kein einziger `gen_ai.*`-Span erscheint.
Es fehlt die Bruecke:

```python
from azure.core.settings import settings as azure_settings
azure_settings.tracing_implementation = "opentelemetry"
```

**4. Das `AzureAISearchTool` braucht einen integrierten Vectorizer im Index.**

```
Query type vector_semantic_hybrid requires a vector field with integrated vectorizer
```

Ein Vektorfeld allein genuegt nicht - der Suchdienst muss die Query selbst
embedden koennen. `01_build_index.py` legt dafuer einen `AzureOpenAIVectorizer`
an; die Managed Identity des Suchdiensts braucht **Cognitive Services OpenAI
User** auf der Foundry-Ressource.

**5. `AIAgentConverter` passt zu keiner der beiden Client-Generationen.**
Er erwartet ein Objekt mit `.agents`, und `.agents` muss der klassische
AgentsClient sein. Der AgentsClient selbst hat kein `.agents`, und
`AIProjectClient` 2.x liefert unter `.agents` etwas anderes:

```
'AgentsClient' object has no attribute 'agents'       # AgentsClient uebergeben
'AgentsOperations' object has no attribute 'runs'     # AIProjectClient 2.x uebergeben
```

`06_evaluation/03_agent_evaluation.py` loest das mit einem Zwei-Zeilen-Adapter.

**6. `TaskAdherenceEvaluator` bewertet in azure-ai-evaluation 1.18.5 falsch.**
Er liefert reproduzierbar `score=0.0` bei einer Begruendung, die das Verhalten
ausdruecklich als korrekt beschreibt. Der Eingabe-Payload ist vollstaendig, der
Fehler liegt im Evaluator. Merksatz: einen Evaluator erst an Faellen mit
bekanntem Ergebnis pruefen, bevor er als Gate in einer Pipeline haengt - sonst
blockiert eine kaputte Metrik das Deployment oder winkt es durch.

---

## Optionale Bausteine

### Azure AI Search (fuer `04_rag/`)

Free-Tier genuegt fuer die Beispiele (inkl. Semantic Ranker).

- Auth auf `aadOrApiKey` stellen, sonst greift Entra ID nicht.
- Dir selbst: **Search Index Data Contributor** + **Search Service Contributor**.
- Der Managed Identity von Foundry-Ressource *und* Projekt: **Search Index Data Reader**.
- Der Managed Identity des Suchdiensts: **Cognitive Services OpenAI User** auf der
  Foundry-Ressource (fuer den Vectorizer).
- Connection im Projekt: Kategorie `CognitiveSearch`, `authType: AAD`.

### Grounding with Bing Search (fuer `03_agents/06`)

- Ressource: `Microsoft.Bing/accounts`, Kind `Bing.Grounding`, SKU `G1`, Region `global`.
- **MSDN-/Sponsorship-Subscriptions koennen die SKU nicht kaufen** (`SkuNotEligible`) -
  dann eine PayAsYouGo-Subscription nutzen. Cross-Subscription funktioniert.
- Connection: Kategorie `GroundingWithBingSearch`, `authType: ApiKey` (AAD wird
  abgelehnt), Target `https://api.bing.microsoft.com/`.
- Nach dem Anlegen ~30s warten: davor kommt ein irrefuehrender `401 Unauthorized`.

### Application Insights (fuer `07_observability/02`)

Log-Analytics-Workspace + App-Insights-Komponente, dann als Connection der
Kategorie `AppInsights` ins Projekt. Danach holt der Code den Connection String
selbst aus dem Projekt - kein zweiter Konfigurationsort.

---

## Konventionen im Code

- **Eine Konfigurationsquelle.** Kein Beispiel liest `os.environ` selbst,
  alles laeuft ueber `common/config.py`.
- **Keine Keys.** `DefaultAzureCredential` ueberall; ein Key-Pfad existiert nur
  als Notausgang.
- **`sys.path`-Shim oben in jeder Datei.** Damit laufen die Skripte direkt per
  `python <ordner>/<datei>.py`, obwohl die Ordner mit Ziffern beginnen und
  deshalb keine Python-Pakete sein koennen.
- **Aufraeumen im `finally`.** Die Beispiele loeschen ihre Agents und Threads.
  In Produktion macht man das *nicht* - siehe `03_agents/10_lifecycle.py` und
  `05_apps/fastapi_chat_api.py`.
- **Modellausgaben mit `markup=False` drucken.** `rich` frisst sonst eckige
  Klammern - eine Antwort mit der Zitatmarke `[handbuch.md#2]` erscheint ohne
  Zitat, und man sucht den Fehler im Prompt statt in der Konsole.

## Wenn etwas nicht laeuft

| Symptom | Ursache |
|---|---|
| `DefaultAzureCredential failed` | `az login` fehlt oder falscher Tenant (`az login --tenant <id>`) |
| `404 DeploymentNotFound` | `MODEL_DEPLOYMENT_NAME` ist der Modell- statt Deployment-Name -> `09_ops/01` |
| `403 PermissionDenied` | Rolle **Foundry User** auf der Ressource fehlt |
| `'AgentsOperations' object has no attribute 'create_agent'` | siehe SDK-Falle 1 |
| `OpenAI.__init__() got an unexpected keyword argument 'api_version'` | siehe SDK-Falle 1 |
| Keine `gen_ai.*`-Spans im Trace | siehe SDK-Falle 3 |
| `requires a vector field with integrated vectorizer` | siehe SDK-Falle 4 |
| `404` bei `embeddings.create` | siehe SDK-Falle 2 |
| `'AgentsOperations' object has no attribute 'runs'` | siehe SDK-Falle 5 |
| `Unsupported parameter: 'top_p'` in einem Agent-Run | Agent-Modell zu neu -> `AGENT_MODEL_DEPLOYMENT_NAME=gpt-4o` |
| `server_error: Sorry, something went wrong.` in einem Agent-Run | GPT-5-Modell + serverseitiges Tool (OpenAPI/Bing/Connected/AI Search) -> `gpt-4o` |
| `Unsupported parameter: 'max_tokens'` | GPT-5-Familie: `max_completion_tokens` nutzen; bei Evaluatoren `is_reasoning_model=True` |
| `Unsupported value: 'temperature'` | GPT-5-Familie akzeptiert nur den Default - Argument weglassen |
| Leere Antwort mit `finish_reason="length"` | `max_completion_tokens` zu klein: das Budget deckt auch die Reasoning-Tokens |
| `ServiceModelDeprecating` beim Deployen | Modellversion abgelaufen: `az cognitiveservices model list -l <region>` |
| `429` | Quota erschoepft -> `09_ops/03_production_hardening.py` |
| Port 8000 belegt | `PORT=8077 python 05_apps/fastapi_chat_api.py` |

## Kosten

Alle Beispiele sind klein gehalten (wenige hundert Tokens pro Lauf). Teurer sind:
`03_agents/06_bing_grounding.py` (Suchgebuehr pro Aufruf),
`06_evaluation/02_batch_evaluate.py` (ein Judge-Aufruf pro Zeile *und* Evaluator)
und alles mit Code Interpreter (Sandbox-Laufzeit). Aufgeraeumt wird jeweils im
`finally` - ausser bei `10_lifecycle.py` und `fastapi_chat_api.py`, die ihre
Agents absichtlich stehen lassen.
