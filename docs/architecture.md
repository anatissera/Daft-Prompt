# Architecture Notes

This branch tests Daft Prompt as a research-only musical assistant.

`PRODUCT.md` is the product source of truth.

## Core Boundaries

- `domain/`: `ReferenceProfile`, `MusicProfile`, research evidence, and `SongState`.
- `application/`: chat orchestration, song research, music Q&A, composition.
- `ports/`: LLM, storage, search, fetching, song research, artifacts.
- `infrastructure/`: web research adapters, storage, LLM providers.
- `interfaces/`: FastAPI HTTP/SSE boundary.

FastAPI routes stay thin. Business behavior belongs in application use cases.

## Research Flow

```text
chat/query
  -> ResearchReference
  -> SongResearcher
  -> WebSearch + PageFetcher + SourceParser
  -> EvidenceFuser
  -> ReferenceProfile
```

The profile stores compact musical claims and cited evidence. It does not store
full tabs, lyrics, or raw scraped pages.

## Composition Flow

The existing multi-agent composer remains isolated:

```text
director
  -> instrument agents
  -> shared SongState negotiation
  -> render artifacts
```

Composition agents consume only compact reference summaries.

## Deployment Shape

The backend is a light container: FastAPI, Pydantic, web research, LLM adapters,
and composition/rendering libraries. Audio/MIR/GPU dependencies are not required
for this branch.

## Verification

- backend unit/API tests with fake research ports;
- frontend typecheck and pure JS tests;
- Docker config/build for the light backend.
