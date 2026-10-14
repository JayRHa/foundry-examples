<!-- jr-brand:start -->
<p align="center">
  <a href="https://jannikreinhard.com/">
    <img src="https://raw.githubusercontent.com/JayRHa/.github/main/assets/readme/brand-header.png" alt="Jannik Reinhard — I help enterprises ship secure AI agents" width="100%">
  </a>
</p>
<p align="center">
  <a href="https://jannikreinhard.com/">Website</a> ·
  <a href="https://www.linkedin.com/in/jannik-r/">LinkedIn</a> ·
  <a href="https://x.com/jannik_reinhard">X</a> ·
  <a href="https://www.youtube.com/@jannikreinhard">YouTube</a>
</p>
<!-- jr-brand:end -->

# Microsoft Agent Framework (optional)

Nachfolger von Semantic Kernel und AutoGen: ein Open-Source-Framework, das
Agents lokal definiert und sie wahlweise gegen Foundry, Azure OpenAI, Anthropic
oder lokale Modelle laufen laesst.

**Wann das statt des Agent Service?**

| | Agent Service (`03_agents/`) | Agent Framework (dieser Ordner) |
|---|---|---|
| Zustand | serverseitig (Threads) | im Prozess (`AgentSession`) |
| Tools | teils serverseitig (Bing, File Search, OpenAPI) | alles lokal |
| Orchestrierung | Connected Agents | Workflows als Graph, Bedingungen, Checkpoints |
| Portabilitaet | an Foundry gebunden | Modellanbieter austauschbar |
| Betrieb | verwaltet | du deployst und skalierst |

Kombinieren ist ueblich: Workflow-Logik im Framework, einzelne Schritte gegen
Modelle oder Agents im Foundry-Projekt.

## Installation

```bash
pip install --pre -r ../requirements-agent-framework.txt
az login
```

> Achtung: Der Install hebt `azure-ai-projects` und `azure-ai-agents` mit an.
> Der Rest des Repos ist gegen genau diesen Stand getestet - also entweder beides
> installieren oder keins.

## Paketstruktur (der haeufigste Stolperstein)

Das Framework ist in viele Pakete zerlegt, und die Foundry-Anbindung ist **nicht**
in `agent_framework.azure`:

| Was | Wo |
|---|---|
| Kern (`Agent`, `WorkflowBuilder`, `AgentSession`) | `agent_framework` |
| Foundry (`FoundryChatClient`, `FoundryAgent`) | `agent_framework_foundry` |

`FoundryChatClient` spricht die Responses API des Projekts und ist der Einstieg
fuer ad-hoc definierte Agents. `FoundryAgent` verbindet sich mit einem Agent,
der bereits **in** Foundry angelegt ist.

## Beispiele

| Datei | Thema |
|---|---|
| `01_basics.py` | Agent als lokales Objekt, Tools als Python-Funktionen, Session, Streaming |
| `02_workflow.py` | Fester Ablauf als Graph (`planer -> autor -> lektorat`) statt freier Delegation |

<!-- jr-brand-footer:start -->
---

[Articles and guides](https://jannikreinhard.com/) · [Repository index](https://github.com/JayRHa/.github/blob/main/REPOSITORIES.md)
<!-- jr-brand-footer:end -->
