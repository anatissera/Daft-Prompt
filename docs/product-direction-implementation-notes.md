# Product Direction Implementation Notes

## Phase 0 Baseline

- Branch: `product-direction`
- Initial worktree state: clean
- Public endpoints to preserve:
  - `POST /chat`
  - `POST /references/research`
  - `POST /references/research/stream`
  - `POST /compose/stream`
  - `GET /health`
  - `POST /references/analyze`
  - `POST /references/analyze/stream`
  - `POST /compose`
- Product source documents kept unchanged:
  - `PRODUCT.md`
  - `DESIGN.md`

## Existing Protection Tests

- Research:
  - `apps/api/tests/test_research_reference.py`
  - `apps/api/tests/test_reference_research_api.py`
  - `apps/api/tests/test_web_research_fusion.py`
- Chat and answer generation:
  - `apps/api/tests/test_chat_music.py`
  - `apps/api/tests/test_answer_music_question.py`
  - `apps/api/tests/test_profile_explainer.py`
  - `apps/api/tests/test_off_topic_gate.py`
- Composition streaming and validation:
  - `apps/api/tests/test_compose_stream.py`
  - `apps/api/tests/test_compose_director_path.py`
  - `apps/api/tests/test_director.py`
  - `apps/api/tests/test_instrument.py`
  - `apps/api/tests/test_validators.py`
  - `apps/api/tests/test_negotiation.py`
- Frontend contracts and playback:
  - `apps/web/lib/trackMixerLogic.test.mjs`
  - `apps/web/lib/chatActionAdapter.test.mjs`
  - `apps/web/lib/referenceProfileView.test.mjs`
  - `apps/web/lib/harmonicFitView.test.mjs`

## Baseline Verification

- `cd apps/api && python -m pytest`: 236 passed, 6 skipped
- `cd apps/web && npm run typecheck`: passed after declaring direct `undici`
  dependency and clearing stale generated `.next` types
- `cd apps/web && node --test lib/trackMixerLogic.test.mjs`: 5 passed
