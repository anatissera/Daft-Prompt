# Superseded Plan - Chat Musical MVP

This plan is historical. It described the older LLMinem direction where local
audio upload and local audio analysis were part of the MVP.

Daft Prompt supersedes that direction. The active roadmap is
`plans/daft-prompt-convergence.md`, and `PRODUCT.md` is the product source of
truth.

Do not implement new user-uploaded file analysis or local audio analysis from
this plan. Song knowledge now comes from evidence connectors such as Songsterr,
tab/chord pages, metadata pages, artist/album information, and style or corpus
references. Legacy audio-analysis code may remain temporarily during migration,
but it is not a supported Daft Prompt product path.

## Historical Summary

The original plan aimed to build a chat-first musical workspace that could:

- analyze local songs;
- answer music questions from a local reference profile;
- compose from scratch;
- compose from an analyzed reference;
- show local playback and compact agent details.

That work remains useful only as background for the chat-first UI, clean
architecture boundaries, and multi-agent composition engine. The source of song
knowledge and the product surface have changed.

## Replacement Direction

Use `plans/daft-prompt-convergence.md` for current implementation phases:

1. Align product/design/architecture docs to Daft Prompt.
2. Define song knowledge, artist style, evidence, playable, tone, and
   composition brief contracts.
3. Strengthen source connectors behind ports, especially Songsterr/tab
   evidence.
4. Build artist/band style profiling.
5. Route chat through song questions, playable views, profiling, composition,
   and generated-song edits.
6. Port the best multi-agent band and rendering work selectively from `giner`.
7. Render requested tabs, keys, rolls, and chord views.
8. Compose from song, artist, album, and genre evidence.
9. Support natural-language edits.
10. Apply the restrained Daft Prompt UI style.

## Current Verification Baseline

```bash
cd apps/api
python -m pytest
```

```bash
cd apps/web
npm run typecheck
node --test lib/trackMixerLogic.test.mjs
```
