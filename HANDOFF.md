# Handoff — style-faithfulness fixes on `feat/style-grounding`

## Contexto

Branch: `feat/style-grounding` (sobre `f7a95c1 feat(style-grounding): add MIDI reader + corpus retrieval + prompt injection`).

Sesión enfocada en que la generación del director sea faithful al estilo pedido, sin hardcodear reglas por género.

## Bugs originales observados

1. **"Chat failed: Error in input stream"** al generar cualquier canción.
   Runs morían justo después del director (sólo `director.json` + `meta.json` en el trace).
2. **Patch desalineado del `instrument` name.**
   En la corrida "buena" archivada (`Downloads/dark_metal(2).mid`) el bass ya venía como bassoon (pgm 70).
   En corridas nuevas el LLM elegía `electric_grand_piano` para un slot `electric_guitar`, o `soprano_sax` para un `synth_lead`.
   El `style_analysis` del director era correcto ("core trio of electric guitar, bass, drums; pianos/brass would clash") pero los patches lo contradecían.

## Fixes aplicados en esta sesión

### 1. `Error in input stream` — streaming toggle
`apps/api/music_assistant/infrastructure/llm.py:203-220`

Antes: `streaming = not is_local` (chequeaba `localhost/127.0.0.1/0.0.0.0`).
Ahora: `streaming = "openrouter.ai" in base_url`.

Sólo el hostname `openrouter.ai` cloud habilita streaming. Cualquier base_url custom (llama-server local, vLLM, LiteLLM, LAN IP, hostname) → `streaming=False`, evita el crash de `langchain_openai` parseando structured output desde chunks non-OpenAI.

### 2. Temperatura por rol
`apps/api/music_assistant/infrastructure/llm.py`

Nuevo `_ROLE_TEMPERATURE = {"director": 0.3, "arbiter": 0.2}` (default `0.7`).
`_build_chat_model(provider, model, settings, role="director")` aplica la temp por rol a Gemini / Groq / OpenRouter / VertexAI.
`_FallbackStructuredInvoker.invoke` pasa `role=self.role`.

Motivo: director elige campos que deben converger al modo del género (roster, key). Instrument agents mantienen `0.7` para no matar expresividad melódica.

### 3. CoT estructurado en el schema del director
`apps/api/music_assistant/agents/director.py` — `DirectorOutput`

Nuevo field `style_analysis: str` posicionado ANTES de `genre` (Pydantic + structured output preserva orden → LLM lo emite primero → decisiones downstream quedan autoregresivamente condicionadas).

System prompt agrega un párrafo previo al listado 1-5:
> "Before anything else, fill `style_analysis` with 2-4 sentences committing to the canonical instrumentation, tempo range, key/mode tendency, and mood of the requested style. Everything you emit afterwards MUST be consistent with what you just committed to here."

### 4. Refactor structural — un solo campo para timbre + label
`apps/api/music_assistant/agents/director.py`

**Removido** `instrument: str` de `ArrangementInstrument` (era free-text y el LLM lo desincronizaba de `patch`).

`patch` (Literal cerrado en `PATCH_SPEC`) es ahora **la única fuente de verdad** para sonido y para el label mostrado al usuario.

- `arrangement_to_song` deriva `RosterItem.instrument = "drum_kit"` si drums, else `str(i.patch)`.
- `_repair_roster_ids` fallback usa `str(item.patch or "")` en vez de `item.instrument`.
- `_collapse_drum_components` construye el kit stub sin `instrument=`.
- System prompt (punto 4 INSTRUMENTATION): "the patch IS the instrument's identity; cross-check every patch against your `style_analysis` before finalising".

Este es el fix que atacó de raíz el bug del `electric_grand_piano` en un slot `electric_guitar` — ya no hay dos campos para desincronizar.

### 5. Tests actualizados
`apps/api/tests/test_director.py`, `test_negotiation.py` — dropped `instrument=` en llamadas a `ArrangementInstrument(...)`.
`test_single_drum_kit_is_left_unchanged` ahora espera `instrument == "drum_kit"` (canónico).
`test_cross_batch_requests_are_not_dispatched_within_batch` identifica al epiano por `"(harmony)"` en el system prompt (el label ya no es "rhodes").
`_make_director_output` en `test_negotiation.py` selecciona patch desde `RosterItem.instrument` si existe en `PATCH_SPEC`, else fallback.

**32/32 tests pass** en `test_director.py` + `test_negotiation.py`.

### 6. `.env` persistente
`apps/api/.env` — creado con:
```
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=local
OPENROUTER_BASE_URL=http://localhost:8080/v1
OPENROUTER_MODEL_DIRECTOR=vllm
OPENROUTER_MODEL_INSTRUMENT=vllm
OPENROUTER_MODEL_ARBITER=vllm
LLM_MAX_RETRIES=1
LLM_RPM_LIMIT=0
```

Antes venía por shell env vars, se perdía al reiniciar uvicorn desde otra sesión.

### 7. Port ledger
`/home/ports.md` — agregadas entradas:
- `3001` Daft-Prompt Next.js dev
- `8000` Daft-Prompt uvicorn backend
- `8080` llama-server (local LLM, modelo `vllm`)

## Estado al hacer el handoff

- Backend uvicorn corriendo en `http://localhost:8000` (pid al momento del handoff: 2301555 — puede haber cambiado).
- Frontend Next dev en `http://localhost:3001`.
- llama-server local en `http://localhost:8080` (modelo id `vllm`).
- Uncommitted en el branch: los fixes 1-5 arriba + el `.env` (que está en `.gitignore` seguramente, verificar antes de commitear).

## Próximo paso pendiente (no arrancado)

**Timing en las trazas.** El usuario quiere hacer la generación más rápida y hoy la traza no tiene `elapsed_ms` por node:

- `meta.json` sólo tiene `started_at`/`ended_at` del run entero.
- `director.json` tiene `written_at` (implícito).
- **No hay `instrument_*.json` ni `arbiter.json`** — que es donde está el bottleneck (varios agentes en paralelo con negociación).

Propuesta acordada al momento del clear:
1. Sumar `elapsed_ms` explícito en cada `write_*` de `infrastructure/tracing.py`.
2. Nuevas funciones `write_instrument(instrument_id, round, elapsed_ms, prompt_messages, output)` y `write_arbiter(elapsed_ms, ...)`, llamadas desde `agents/instrument.py` y el nodo de convergence.
3. `write_meta` final con breakdown: `{director_ms, instruments_total_ms, arbiter_ms, render_ms, total_ms}`.

Con eso el usuario ve en 1-2 corridas dónde se va el tiempo antes de decidir qué optimizar.

## Observaciones de reference sobre el corpus

- El retrieval de `retrieve_style_examples` puede devolver múltiples progresiones del **mismo `track_id`** (ver trace `e8fdf9da1de4/director.json` — todas las 3 canonical progressions eran de `TRGBSRZ128F9306EA9`). No es un blocker ahora, pero limita diversidad. Fix futuro: dedupe por `track_id` en `retrieve.py` antes del top-k.
- El corpus tag para "metal" tiene tracks etiquetados en E major (probable mislabel del MSD source). El `style_analysis` reciente sobreescribe esto al pedirle al LLM que decida key idiomática desde su propio conocimiento del género.
