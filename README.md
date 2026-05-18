# exara-agent

[![PyPI](https://img.shields.io/pypi/v/exara-agent.svg)](https://pypi.org/project/exara-agent/)
[![Python](https://img.shields.io/pypi/pyversions/exara-agent.svg)](https://pypi.org/project/exara-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## English

**Local-first autonomous AI agent for programming and system automation.** Exara runs with local models (Ollama, vLLM, LM Studio, llama.cpp) or any OpenAI-compatible API (OpenRouter, OpenAI, DeepSeek, Anthropic, Groq) using native tool calling. It ships with a Rich CLI, a Next.js web UI, and MCP support for GitHub, filesystem, Slack, Linear, Postgres, browser automation, and more.

## Espanol

**Agente de IA local-first para programacion y automatizacion del sistema.** Exara funciona con modelos locales (Ollama, vLLM, LM Studio, llama.cpp) o con cualquier API compatible con OpenAI (OpenRouter, OpenAI, DeepSeek, Anthropic, Groq) usando tool calling nativo. Incluye CLI con Rich, interfaz web en Next.js y soporte MCP para GitHub, filesystem, Slack, Linear, Postgres, automatizacion de navegador y mas.

```bash
pip install exara-agent
exara init      # one-time setup / configuracion inicial
exara chat      # chat from any folder / chat desde cualquier carpeta
```

---

## What it does / Que hace

| English | Espanol |
|---|---|
| ReAct loop with native tool calling, not fragile JSON parsing. | Loop ReAct con tool calling nativo, sin depender de JSON fragil. |
| 30+ built-in tools: file ops, multi-edit, search, shell, Python, git, packages, web fetch, vision, audio, todos, plan mode, and delegation. | 30+ herramientas: archivos, multi-edit, busqueda, shell, Python, git, paquetes, web fetch, vision, audio, todos, plan mode y delegacion. |
| MCP client: add servers in `~/.ai-agent/mcp.json` or `./mcp.json`. | Cliente MCP: agrega servidores en `~/.ai-agent/mcp.json` o `./mcp.json`. |
| Skills system: markdown knowledge packs auto-loaded by project stack. | Sistema de skills: paquetes markdown de conocimiento cargados por stack. |
| Multi-provider profiles: switch with `exara profile use <name>`. | Perfiles multi-proveedor: cambia con `exara profile use <name>`. |
| Permission levels: `safe`, `normal`, `full`, plus destructive-command denylist. | Niveles de permisos: `safe`, `normal`, `full`, mas denylist de comandos destructivos. |
| Streaming responses, diff previews, hooks, Docker sandbox, and secret redaction. | Streaming, previews de diff, hooks, sandbox Docker y redaccion de secretos. |

---

## Install / Instalacion

```bash
pip install exara-agent
```

Recommended global isolation / Aislamiento global recomendado:

```bash
pipx install exara-agent
```

One-line installers / Instaladores de una linea:

```bash
# macOS / Linux
curl -sSL https://raw.githubusercontent.com/santirivera-oss/exara-agent/main/scripts/install.sh | bash
```

```powershell
# Windows PowerShell
iwr https://raw.githubusercontent.com/santirivera-oss/exara-agent/main/scripts/install.ps1 | iex
```

### First run / Primer inicio

```bash
exara init
```

English: runs the interactive setup wizard. It picks a provider, asks for an API key, optionally enables MCP servers, and writes a starter skill at `~/.ai-agent/skills/my-preferences.md`.

Espanol: ejecuta el asistente interactivo. Elige proveedor, pide una API key, opcionalmente activa servidores MCP y escribe una skill inicial en `~/.ai-agent/skills/my-preferences.md`.

### Sanity check / Revision rapida

```bash
exara doctor       # provider, tools, memory, launchers, MCP
exara doctor --fix # create safe missing local dirs/configs
exara skills list  # active skills in this cwd
exara mcp list     # configured MCP servers and tools
```
---

## Use it / Uso

```bash
# One-shot task / tarea de una sola ejecucion
exara run "summarise the structure of this project"

# Interactive REPL / chat interactivo
exara chat

# Web UI / interfaz web
exara serve   # http://127.0.0.1:8765
cd frontend && npm run dev   # http://localhost:3100
```

### Chat slash commands / Comandos dentro del chat

```text
/help     /tools    /sessions       /resume <id>
/model    /plan     /init           /compact
/stats    /todos    /ps             /clear
```

### Full command reference / Referencia completa de comandos

- [`docs/COMMANDS.md`](docs/COMMANDS.md) - every CLI command, MCP/profile/skills/memory command, and chat slash command in English and Spanish.
- [`docs/COMMANDS.md`](docs/COMMANDS.md) - todos los comandos del CLI, MCP/profile/skills/memory y slash commands del chat en ingles y espanol.

---

## Providers / Proveedores

Anything OpenAI-compatible works out of the box.

Cualquier proveedor compatible con OpenAI funciona de fabrica.

| Preset | Endpoint | Default model / Modelo default |
|---|---|---|
| `ollama-local` | http://localhost:11434 | `qwen2.5:7b-instruct` |
| `openrouter` | https://openrouter.ai/api/v1 | `deepseek/deepseek-chat` |
| `openai` | https://api.openai.com/v1 | `gpt-4o-mini` |
| `anthropic` | https://api.anthropic.com/v1 | `claude-haiku-4-5` |
| `deepseek` | https://api.deepseek.com/v1 | `deepseek-chat` |
| `groq` | https://api.groq.com/openai/v1 | `llama-3.3-70b-versatile` |
| `lm-studio` | http://localhost:1234/v1 | whatever you loaded / el modelo que cargues |

```bash
exara profile presets       # show presets / ver presets
exara profile add --from openrouter --use
exara profile use ollama-local
```

Inside chat / Dentro del chat:

```text
/model minimax/minimax-m2.5:free
/model deepseek/deepseek-chat
```

---

## Permission levels / Niveles de permisos

| Level / Nivel | Reads / Lecturas | Writes, shell, Python / Escritura, shell, Python | Confirmation / Confirmacion |
|---|---|---|---|
| `safe` | yes / si | denied / denegado | n/a |
| `normal` | yes / si | allowed / permitido | required on high-risk actions / requerida en acciones de riesgo |
| `full` | yes / si | allowed / permitido | skipped / omitida |

English: destructive command patterns (`rm -rf /`, `mkfs.*`, `format c:`, etc.) are blocked at every level via the bundled `default_config.yaml`.

Espanol: los patrones destructivos (`rm -rf /`, `mkfs.*`, `format c:`, etc.) se bloquean en todos los niveles desde el `default_config.yaml` incluido.

---

## Config layout / Estructura de configuracion

```text
~/.ai-agent/
|-- profiles.json        # provider keys / keys de proveedores
|-- mcp.json             # global MCP servers / MCPs globales
|-- config.yaml          # optional global overrides / overrides globales opcionales
|-- skills/              # global skills / skills globales
|   `-- my-preferences.md
|-- data/agent.db        # SQLite memory / memoria SQLite
`-- logs/                # JSON logs

./                        # per-workspace overrides / overrides por workspace
|-- .env                  # env vars, highest precedence / maxima prioridad
|-- config.yaml           # workspace-only config / config del workspace
|-- mcp.json              # workspace MCP servers / MCPs del workspace
`-- skills/               # workspace skills / skills del workspace
```

Precedence / Prioridad:

```text
bundled defaults -> ~/.ai-agent/config.yaml -> workspace config.yaml -> active profile -> AI_AGENT_* env vars
```
---

## Architecture & docs / Arquitectura y documentacion

| Document | English | Espanol |
|---|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Internals, ReAct loop, tool registry. | Internals, loop ReAct y registro de tools. |
| [`docs/MCP.md`](docs/MCP.md) | How MCP integration works. | Como funciona la integracion MCP. |
| [`docs/COMMANDS.md`](docs/COMMANDS.md) | Bilingual CLI command reference. | Referencia bilingue de comandos CLI. |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | What is next. | Que sigue. |
| [`CHANGELOG.md`](CHANGELOG.md) | Release notes. | Notas de version. |

---

## Develop / Desarrollo

```bash
git clone https://github.com/santirivera-oss/exara-agent
cd exara-agent
python -m venv .venv
. .venv/Scripts/Activate.ps1     # PowerShell on Windows
# source .venv/bin/activate      # macOS / Linux
pip install -e ".[dev]"
pytest

# Web UI / interfaz web
cd frontend
npm install
npm run dev                      # http://localhost:3100
```

---

## License / Licencia

MIT - see [LICENSE](LICENSE).

MIT - ver [LICENSE](LICENSE).