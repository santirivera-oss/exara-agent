# Exara Agent Command Reference / Referencia de Comandos

This page lists the main Exara Agent commands in English and Spanish.

Esta pagina lista los comandos principales de Exara Agent en ingles y espanol.

## Main CLI / CLI principal

| Command | English | Espanol |
|---|---|---|
| `exara --help` | Show all top-level commands. | Muestra todos los comandos principales. |
| `exara init` | Run the interactive first-run setup wizard. | Ejecuta el asistente interactivo de configuracion inicial. |
| `exara chat` | Start the interactive agent REPL in the current folder. | Inicia el chat interactivo del agente en la carpeta actual. |
| `exara chat --model <model-id>` | Start chat with a temporary model override. | Inicia el chat usando temporalmente otro modelo. |
| `exara chat --provider <provider>` | Start chat with a temporary provider override (`ollama` or `openai_compat`). | Inicia el chat usando temporalmente otro proveedor (`ollama` u `openai_compat`). |
| `exara chat --permission <safe|normal|full>` | Start chat with a specific permission level. | Inicia el chat con un nivel de permisos especifico. |
| `exara chat --workspace <path>` | Start chat against a specific workspace path. | Inicia el chat usando una carpeta de workspace especifica. |
| `exara run "<task>"` | Run one non-interactive task and exit. | Ejecuta una tarea sin entrar al chat interactivo. |
| `exara run "<task>" --yes` | Run one task and auto-confirm gated actions. Use carefully. | Ejecuta una tarea y confirma automaticamente acciones bloqueadas. Usalo con cuidado. |
| `exara models` | List models available from the configured provider. | Lista los modelos disponibles del proveedor configurado. |
| `exara doctor` | Check provider connectivity, memory, tools, launchers, and MCP visibility. | Revisa proveedor, memoria, tools, launchers y MCPs visibles. |
| `exara doctor --fix` | Create safe missing local directories/config files. | Crea carpetas/configs locales seguros si faltan. |
| `exara tools` | List built-in Exara tools. | Lista las herramientas internas de Exara. |
| `exara serve` | Start the FastAPI backend server. | Inicia el servidor backend FastAPI. |
| `exara serve --host <host> --port <port>` | Start the API server on a custom host/port. | Inicia el API server en host/puerto personalizados. |

## Model Profiles / Perfiles de modelo

Profiles are stored in `~/.ai-agent/profiles.json` so API keys stay out of the repo.

Los perfiles se guardan en `~/.ai-agent/profiles.json` para que las API keys no entren al repo.

| Command | English | Espanol |
|---|---|---|
| `exara profile list` | Show saved provider profiles and mark the active one. | Muestra perfiles guardados y marca el activo. |
| `exara profile presets` | Show built-in provider presets. | Muestra presets incluidos de proveedores. |
| `exara profile add` | Add/update a profile interactively. | Agrega o actualiza un perfil de forma interactiva. |
| `exara profile add --from openrouter --use` | Create an OpenRouter profile from the preset and activate it. | Crea un perfil OpenRouter desde preset y lo activa. |
| `exara profile add --from ollama-local --use` | Create a local Ollama profile and activate it. | Crea un perfil local de Ollama y lo activa. |
| `exara profile use <name>` | Switch the active profile. | Cambia el perfil activo. |
| `exara profile show` | Show the active profile with masked API key. | Muestra el perfil activo con API key enmascarada. |
| `exara profile show <name>` | Show a specific profile. | Muestra un perfil especifico. |
| `exara profile remove <name>` | Delete a saved profile. | Elimina un perfil guardado. |

## MCP Commands / Comandos MCP

MCP servers can be installed globally in `~/.ai-agent/mcp.json` or per-workspace in `./mcp.json`.

Los servidores MCP pueden instalarse globalmente en `~/.ai-agent/mcp.json` o por proyecto en `./mcp.json`.

| Command | English | Espanol |
|---|---|---|
| `exara mcp list` | Show configured MCP servers and the tools they expose. | Muestra MCPs configurados y sus herramientas. |
| `exara mcp catalog` | Show the curated MCP server catalogue. | Muestra el catalogo curado de servidores MCP. |
| `exara mcp install <name>` | Install an MCP server into the current workspace config. | Instala un MCP en la configuracion del workspace actual. |
| `exara mcp install <name> --global` | Install an MCP server globally so it works from any folder. | Instala un MCP global para usarlo desde cualquier carpeta. |
| `exara mcp install <name> --disabled` | Add a server as disabled without auto-loading it. | Agrega un servidor deshabilitado sin cargarlo automaticamente. |
| `exara mcp test <server> <tool> --args '{"key":"value"}'` | Call one MCP tool directly to verify it works. | Ejecuta una herramienta MCP directamente para probarla. |
| `exara mcp test filesystem list_directory --args '{"path":"."}'` | Example filesystem MCP test. | Ejemplo para probar el MCP filesystem. |

## Skills Commands / Comandos de Skills

Skills are markdown knowledge packs loaded from bundled skills, `~/.ai-agent/skills/`, and `./skills/`.

Las skills son paquetes markdown de conocimiento cargados desde skills incluidas, `~/.ai-agent/skills/` y `./skills/`.

| Command | English | Espanol |
|---|---|---|
| `exara skills list` | Show all skills and which ones are active in the current workspace. | Muestra todas las skills y cuales estan activas en el workspace actual. |
| `exara skills show <name>` | Print the full body of one skill. | Muestra el contenido completo de una skill. |

## Memory Commands / Comandos de Memoria

Memory facts are stored in SQLite and scoped by workspace unless `--all` is used.

Los hechos de memoria se guardan en SQLite y se separan por workspace salvo que uses `--all`.

| Command | English | Espanol |
|---|---|---|
| `exara memory list` | List memory facts for the current workspace. | Lista la memoria del workspace actual. |
| `exara memory list --all` | List memory facts from every workspace. | Lista memoria de todos los workspaces. |
| `exara memory set <key> <value>` | Save or update one memory fact. | Guarda o actualiza un dato de memoria. |
| `exara memory search <query>` | Search memory facts in the current workspace. | Busca datos de memoria en el workspace actual. |
| `exara memory search <query> --all` | Search memory facts across all workspaces. | Busca datos de memoria en todos los workspaces. |
| `exara memory forget <key>` | Delete one memory fact after confirmation. | Borra un dato de memoria con confirmacion. |
| `exara memory forget <key> --yes` | Delete one memory fact without prompting. | Borra un dato de memoria sin preguntar. |

## Chat Slash Commands / Comandos dentro del chat

Run these inside `exara chat`.

Ejecutalos dentro de `exara chat`.

| Slash command | English | Espanol |
|---|---|---|
| `/help` | Show chat help. | Muestra ayuda del chat. |
| `/clear` | Start a fresh session while keeping the agent running. | Inicia una sesion nueva sin cerrar el agente. |
| `/tools` | List registered tools available to the model. | Lista herramientas disponibles para el modelo. |
| `/sessions` | List recent sessions. | Lista sesiones recientes. |
| `/resume <id>` | Resume a previous session. | Reanuda una sesion anterior. |
| `/model <model-id>` | Switch model at runtime for the current chat. | Cambia de modelo en caliente para el chat actual. |
| `/plan` | Toggle read-only plan mode. | Activa/desactiva modo plan de solo lectura. |
| `/init` | Ask the agent to write project instructions (`CLAUDE.md`). | Pide al agente escribir instrucciones del proyecto (`CLAUDE.md`). |
| `/compact` | Summarize old history to free context window. | Resume historial viejo para liberar contexto. |
| `/stats` | Show message count, model, provider, and plan mode state. | Muestra conteo de mensajes, modelo, proveedor y estado de plan mode. |
| `/todos` | Show current session todos. | Muestra tareas/todos de la sesion. |
| `/ps` | List background processes started by the agent. | Lista procesos en background iniciados por el agente. |
| `/profile` | List profiles from inside chat. | Lista perfiles desde el chat. |
| `/profile use <name>` | Activate a profile from inside chat. Restart chat to apply. | Activa un perfil desde el chat. Reinicia el chat para aplicarlo. |
| `/exit`, `/quit`, `/q` | Exit chat. | Sale del chat. |

## Common Workflows / Flujos comunes

### First setup / Primera configuracion

```powershell
pip install exara-agent
exara init
exara doctor --fix
exara chat
```

### Use OpenRouter / Usar OpenRouter

```powershell
exara profile add --from openrouter --use
exara chat
```

Inside chat / Dentro del chat:

```text
/model minimax/minimax-m2.5:free
```

### Install useful MCPs globally / Instalar MCPs utiles globalmente

```powershell
exara mcp catalog
exara mcp install filesystem --global
exara mcp install memory --global
exara mcp install github --global
exara mcp list
```

### Save project memory / Guardar memoria del proyecto

```powershell
exara memory set stack "python+nextjs"
exara memory set preference "Spanish answers, concise explanations"
exara memory list
```
