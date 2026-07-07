#!/usr/bin/env bash
set -euo pipefail

API="${API:-http://localhost:8000}"
QUERY="${1:-Another One Bites the Dust Queen}"
SIMILAR_MESSAGE="${2:-Componé algo nuevo con un bajo parecido al de esta canción}"
LITERAL_MESSAGE="${3:-Intentá hacer una canción entera lo más igual posible a esta referencia. Copiá literalmente todos los instrumentos y secciones para los que tengas notas simbólicas reales; si falta evidencia para algún instrumento o sección, componelo lo más parecido posible y avisá exactamente qué no pudiste copiar literal.}"
OUT_DIR="${OUT_DIR:-/tmp/llminem-smoke}"

mkdir -p "$OUT_DIR"

research() {
  curl -s "$API/references/research" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg query "$QUERY" '{query: $query}')"
}

compose() {
  local ref_id="$1"
  local message="$2"
  curl -s "$API/chat" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg message "$message" --arg reference_id "$ref_id" '{message: $message, reference_id: $reference_id}')"
}

check_literal_response() {
  local response="$1"
  local failed=0
  local transfer_mode
  local applied
  local note_pack_id
  local literal_summary
  local drums_applied
  local drums_null_pitches

  if ! jq -e '.compose != null' <<<"$response" >/dev/null; then
    echo "[FAIL] literal smoke expected compose payload, got compose=null"
    return 1
  fi

  transfer_mode="$(jq -r '
    .compose.reference_transfer_intent.items[]?
    | select(.instrument_family == "bass")
    | .transfer_mode
  ' <<<"$response" | head -n 1)"
  applied="$(jq -r '
    .compose.literal_applications[]?
    | select(.instrument_family == "bass")
    | .applied
  ' <<<"$response" | head -n 1)"
  note_pack_id="$(jq -r '
    .compose.literal_applications[]?
    | select(.instrument_family == "bass")
    | .note_pack_id
  ' <<<"$response" | head -n 1)"
  literal_summary="$(jq -r '
    (.compose.song.parts // {})
    | to_entries[]
    | select((.key | test("bass|low_end"; "i")) or ((.value.notes_summary // "") | contains("literal reference pack")))
    | .value.notes_summary
  ' <<<"$response" | head -n 1)"
  drums_applied="$(jq -r '
    .compose.literal_applications[]?
    | select(.instrument_family == "drums")
    | .applied
  ' <<<"$response" | head -n 1)"
  drums_null_pitches="$(jq -r '
    (.compose.song.parts.drums.notes // [])
    | if length == 0 then "empty" elif all(.pitch == null) then "all_null" else "has_pitch" end
  ' <<<"$response")"

  if [[ "$transfer_mode" != "literal" ]]; then
    echo "[FAIL] literal smoke expected bass transfer_mode=literal, got: ${transfer_mode:-<empty>}"
    failed=1
  fi
  if [[ "$applied" != "true" ]]; then
    echo "[FAIL] literal smoke expected literal_application applied=true, got: ${applied:-<empty>}"
    failed=1
  fi
  if [[ -z "$note_pack_id" || "$note_pack_id" == "null" ]]; then
    echo "[FAIL] literal smoke expected non-empty note_pack_id"
    failed=1
  fi
  if [[ "$literal_summary" != literal\ reference\ pack* ]]; then
    echo "[FAIL] literal smoke expected bass notes_summary to start with 'literal reference pack', got: ${literal_summary:-<empty>}"
    failed=1
  fi
  if [[ "$drums_applied" == "true" && "$drums_null_pitches" != "has_pitch" ]]; then
    echo "[FAIL] literal smoke expected literal drums to contain audible GM pitches, got: $drums_null_pitches"
    failed=1
  fi
  return "$failed"
}

reference_json="$(research)"
ref_id="$(jq -r '.reference_id' <<<"$reference_json")"
echo "reference_id=$ref_id"

echo "== instrument profiles =="
profiles_json="$(curl -s "$API/references/$ref_id/instrument-profiles")"
jq '{reference_id, profiles: [.profiles[] | {instrument_family, track_name, note_packs, musical_memory_summary}]}' <<<"$profiles_json"

if ! jq -e 'any(.profiles[]?; .instrument_family == "bass" and ((.note_packs // []) | length > 0))' <<<"$profiles_json" >/dev/null; then
  echo "[FAIL] expected bass.note_packs to be non-empty before literal composition"
  exit 1
fi

for mode in similar literal; do
  if [[ "$mode" == "similar" ]]; then
    message="$SIMILAR_MESSAGE"
  else
    message="$LITERAL_MESSAGE"
  fi
  echo "== compose $mode =="
  response="$(compose "$ref_id" "$message")"
  jq '{
    intent,
    reply,
    error,
    transfer: .compose.reference_transfer_intent,
    instrument_requests_summary: .compose.instrument_requests_summary,
    literal_applications: .compose.literal_applications,
    warnings: .compose.warnings,
    part_summaries: (.compose.song.parts // {} | with_entries(.value = .value.notes_summary)),
    first_events: {
      bass: ((.compose.song.parts.bass.notes // [])[:12]),
      drums: ((.compose.song.parts.drums.notes // [])[:12]),
      guitar: ((.compose.song.parts.guitar.notes // [])[:12])
    },
    midi: .compose.artifacts.midi
  }' <<<"$response"
  if [[ "$mode" == "literal" ]]; then
    check_literal_response "$response"
  fi
  midi_url="$(jq -r '.compose.artifacts.midi // empty' <<<"$response")"
  if [[ -n "$midi_url" ]]; then
    curl -s -L "$midi_url" -o "$OUT_DIR/$mode.mid"
    echo "saved $OUT_DIR/$mode.mid"
  fi
done
