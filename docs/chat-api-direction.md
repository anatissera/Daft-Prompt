# Chat API Direction

This note documents how the current frontend talks to the backend, and how that
should evolve toward the chat-first product described in `PRODUCT.md` and
`DESIGN.md`.

The current UI is intentionally chat-first, but the backend still exposes
separate MVP endpoints for reference analysis and composition. That is useful
for iteration, but the product direction is a single conversational backend
entrypoint that routes user intent in the application layer.

## Current Endpoints

| Surface | Endpoint | Responsibility |
| --- | --- | --- |
| FastAPI backend | `POST /references/analyze` | Accept one local audio upload and return a compact `ReferenceProfile`. |
| FastAPI backend | `POST /compose/stream` | Accept a text style/prompt and stream composition SSE events until a final `done` event. |
| Next.js proxy | `POST /api/references/analyze` | Forward browser uploads to the backend without exposing backend routing details to UI components. |
| Next.js proxy | `POST /api/compose` | Forward the backend composition SSE stream as a same-origin browser request. |

`POST /references/analyze` is local-file only for the MVP. It should continue to
return probabilistic musical analysis: likely tempo, likely key, energy/section
estimates, and probable chords with confidence. Chord, key, beat, and section
estimates must not be presented as certain facts.

`POST /compose/stream` is the current composition path. It emits director,
agent-pass, convergence/error, and final done events. The frontend renders the
final song as contextual chat output with playback, mixer controls, MIDI export,
and optional technical details.

## Future `/chat` Endpoint

A future backend endpoint should make chat orchestration explicit:

```text
POST /chat
  input: user message, optional local attachment metadata or upload reference,
         current ReferenceProfile, optional generated song context
  output: assistant message events and typed result blocks
```

The backend application layer should decide whether a turn means:

- analyze an attached local audio file;
- answer a question from the current `ReferenceProfile`;
- compose from scratch;
- compose from the current reference profile;
- ask one short clarification when intent is ambiguous.

The frontend should not own musical business rules. It may keep temporary local
helpers while `/chat` does not exist, but those helpers should be treated as an
adapter over the current split endpoints, not as the final architecture.

## Responsibility Boundaries

| Layer | Should do | Should not do |
| --- | --- | --- |
| Frontend | Render chat, collect user input, attach local files, show progress, call API routes, play generated output. | Decide durable musical business rules, analyze audio, or implement composition policy. |
| Backend `interfaces/` | Keep FastAPI routes thin: validate HTTP input, call use cases, return responses or streams. | Contain chat routing, analysis policy, or composition defaults directly in route handlers. |
| Backend `application/` | Route conversational intent, orchestrate analysis, explanation, composition, and clarification. | Import provider-specific adapters directly or leak infrastructure details to the UI. |
| Backend `domain/` and `ports/` | Define stable concepts and dependency contracts such as `ReferenceProfile`, `SongState`, analyzers, storage, and LLM providers. | Depend on FastAPI, React, local UI state, or provider-specific response shapes. |
| Backend `infrastructure/` | Implement ports for MIR, storage, rendering, transcription, stems, and LLM providers. | Decide product-level chat behavior. |

## Migration Guidance

Until `/chat` exists, the frontend can keep a small adapter that maps a chat
turn to the current endpoints:

- selected file means call `/api/references/analyze`;
- reference question means answer from the current profile;
- otherwise call `/api/compose`.

When `/chat` is added, replace that adapter with one client call that consumes
typed chat events. The chat UI should be able to keep rendering text, analysis
blocks, composition blocks, progress, and errors without a major redesign.
