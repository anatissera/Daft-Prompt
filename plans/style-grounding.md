# Style Grounding — replaneado sobre `develop`

Objetivo: que Director + instrumentos compongan con lógica musical y apegados al estilo declarado.
Este documento asume el estado actual del branch `develop` (rama `music_assistant/`, no `llm_band/`), no del branch `main`.

---

## 0. Estado actual del repo (ground truth, no repetir lo que ya está)

Antes de proponer nada, esto es lo que YA existe en `develop`:

**Director** (`agents/director.py`) ya emite:
- `chord_progression`: un `ChordSpan` por bar con símbolos tipo `"Dm7"`, `"G7"` (no romanos).
- `sections` con `energy` en `{low, medium, high}`.
- `playing_style` por instrumento (1-2 frases de técnica idiomática).
- `composition_groups` para composición por capas.
- Off-topic gate, drum-collapse repair, ID slugger.

**Prompt de instrumento** (`agents/instrument.py::_system_prompt`) ya inyecta:
- Chord map por bar con **chord tone names** (`_chord_map_text` — ej. `bar 3: G7 (chord tones: G, B, D, F)`).
- Section map con `energy`.
- `playing_style` del instrumento.
- Peer summaries.
- Guidance para landing en chord tones y passing tones.

**Validators** (`music/validators.py`) ya chequean:
- Bar / beat / duración / velocity / range MIDI / bar overflow.
- Empty part.
- `out_of_key` warning cuando la nota no entra ni en el acorde ni en la key (chord-aware).
- Drums exentos de range y armonía.

**Métricas** (`music/validators.py::harmonic_fit`) — fracción de notas evaluables que son chord tones.

**Theory helpers** (`music/theory.py`) — wrappers de `music21` cacheados: `chord_pitch_classes`, `chord_tone_names`, `active_chord_at`, `in_key`, `beats_per_bar`.

**Export MIDI** (`music/render_midi.py`, `music/to_music21.py`) — `SongState → .mid` y `→ MusicXML` para engrave.

**Repair loop** — cada instrumento hace hasta `MAX_REPAIRS=2` de repair sobre errores de validator.

## Lo que sigue faltando (donde hay ROI real)

1. **Lectura de MIDI** — no existe. Sin esto, ningún corpus externo sirve.
2. **Retrieval de estilo** — el Director recibe sólo el string del usuario. No hay corpus, no hay ejemplos canónicos, no hay progresiones típicas por género, no hay grooves de referencia.
3. **`note_density`** — utilidad chica que falta para eval y matching de retrieval.
4. **`detect_overlaps`** — instrumentos monofónicos (bass, lead) pueden emitir notas superpuestas y no se detecta.
5. **MIDI grid concreta en el prompt** — hoy se pasan chord tone *names* ("G, B, D, F"). Sería un bump traducirlo a MIDI ints filtrados por el range del instrumento (`allowed_pitches`). Marginal frente al 1-4, se ve al final.
6. **Voice-leading / paralelas** — quality-of-life, no crítico.
7. **Arbiter con tools** — v2.

---

## Nuevo plan (ordenado por ROI y dependencias)

### Fase 1 — MIDI reader + utilidades chicas

**Qué se hace:**
- Crear `music_assistant/music/read_midi.py`, espejo de `render_midi.py`:
  - `read_midi(path: str) → ReadSong` con `pretty_midi.PrettyMIDI(path)`.
  - `ReadSong` — dataclass aparte de `SongState` para que un track ajeno no entre por accidente al grafo runtime.
  - Extractores puros: `extract_key(read_song)`, `extract_progression(read_song)` (chroma → template matching → símbolos tipo `"Cmaj7"`, mismo formato que Director), `extract_drum_pattern(read_song)`, `extract_density_by_role(read_song)`.
- Agregar a `music/theory_tools.py` (nuevo módulo delgado, no pisar `theory.py`):
  - `note_density(part, header) → notas/bar` por instrumento.
  - `detect_overlaps(part, is_monophonic: bool)` → lista de issues.
- Tests: unitarios de cada extractor con `pretty_midi` sintético, más un **round-trip** — render un `SongState` conocido, leerlo con `read_midi`, verificar equivalencia módulo cuantización. Ese round-trip es el gate de correctness del reader.

**Qué NO se hace:** nada que cambie comportamiento runtime. Todo aditivo. La única cosa que se puede sumar sin fricción es meter `detect_overlaps` en `validate_song` con severity `error` para instrumentos monofónicos por convención (bass, lead) — dispara el repair loop existente.

**Criterio de aceptación:** tests verdes, round-trip pasa, `pytest tests/test_read_midi.py tests/test_theory_tools.py`.

### Fase 2 — Fetch + índice del corpus chico (Magenta Groove)

**Qué se hace:**
- `scripts/fetch_corpora.py` — descarga `groove-v1.0.0-midionly.zip` (~5 MB), verifica hash, descomprime a `apps/api/data/groove/`. Idempotente.
- `music_assistant/corpus/groove_index.py`:
  - Lee `info.csv` (drummer, style, bpm, time_signature, type=beat/fill, split).
  - Por MIDI, corre `read_midi` + `extract_drum_pattern`.
  - Escribe `data/index/groove_patterns.parquet` con `[style, bpm, time_sig, type, bars, pattern_by_channel]`.
- `.gitignore` para `apps/api/data/`.

**Qué NO se hace:** Lakh todavía. Groove primero porque es 5 MB, valida el approach, y la ganancia audible del drum template es enorme sola.

**Criterio de aceptación:** parquet generado, tests unitarios del indexer con MIDIs de fixture chicos.

### Fase 3 — Fetch + índice del corpus grande (Lakh)

**Qué se hace:**
- Agregar a `fetch_corpora.py` la descarga de `lmd_matched.tar.gz` (~1.6 GB) y el mapping Tagtraum (`msd_tagtraum_cd2c.cls`).
- `music_assistant/corpus/lakh_index.py`:
  - Por MIDI (paralelizado con `multiprocessing.Pool` — 45k archivos):
    1. `read_midi`.
    2. `extract_key`, `extract_progression`, `extract_density_by_role`, lista de GM programs.
    3. Cross-ref `msd_tagtraum` → asignar género.
    4. Segmentar en ventanas de 8 bars.
  - Output: `data/index/lakh_segments.parquet` con `[track_id, genre, key, tempo, bar_start, bar_end, progression_symbols, density_by_role, gm_programs]`.
- Costo: ~2-3h en un core; con Pool de 8, ~20 min. Aceptable, corre una vez.

**Criterio de aceptación:** parquet generado, spot-check de 10 filas por género razonable.

### Fase 4 — Módulo de retrieval

**Qué se hace:**
- `music_assistant/corpus/retrieve.py`:
  - `retrieve_style_examples(genre: str, section_energy: str, key: str, n: int = 2) → list[LakhExample]`. Filtra por género fuzzy, luego por densidad matching energy (low/medium/high → percentiles), transpone progresión a la key pedida.
  - `retrieve_groove(style: str, bpm: float, section_energy: str) → GroovePattern`. Match style + bpm ±10% + type (beat para verse/chorus, fill para transiciones).
  - `normalize_genre(user_string: str) → list[str]` — one-shot LLM llamada cacheada que mapea "reggaeton perreo" a `["reggaeton", "latin urban"]`, tags del corpus.
- **Contrato clave**: el LLM nunca ve MIDI. Todo lo que devuelve `retrieve.py` es símbolo compacto listo para prompt.
- Fallback: si el corpus no está en disco (CI, dev fresco), retornar listas vacías sin crashear. El pipeline degrada al comportamiento actual.
- Tests con índices fake.

**Criterio de aceptación:** tests con genre fuzzy match, con corpus vacío, y una sanity check contra el índice real.

### Fase 5 — Director recibe style card

**Qué se hace:**
- En `agents/director.py::run_director`, antes de armar el prompt:
  1. Llamar `retrieve_style_examples(style, "medium", key=None, n=3)`.
  2. Formatear como bloque de contexto: progresiones canónicas (símbolos), instrumentación GM más frecuente, rango de BPM.
- Meter el bloque en el prompt como user message adicional después del system, tipo:
  ```
  Canonical examples for this style (guidance, not override):
  - track A: key=Cm, bpm=92, progression: Cm | Ab | Eb | Bb ×2, instrumentation: bass, drums, pad, lead
  - track B: ...
  ```
- Semántica: guidance, no hard constraint. El Director sigue tomando la decisión final.
- Si el retrieval devuelve vacío (corpus off), el prompt queda igual que ahora.

**Criterio de aceptación:** con corpus, tests que confirmen que la style card aparece en el prompt; run manual con estilo conocido muestra progresión razonable.

### Fase 6 — Drum recibe groove template

**Qué se hace:**
- En `agents/instrument.py::_system_prompt`, cuando `roster_item.is_drum`:
  1. Llamar `retrieve_groove(header.genre, header.tempo_bpm, section_energy_of_current_bar)`.
  2. Formatear el patrón como bloque de referencia:
     ```
     Reference groove for this style (adapt, don't copy blindly):
       kick:  x . . . x . . . x . . . x . . .
       snare: . . . . x . . . . . . . x . . .
       hihat: x . x . x . x . x . x . x . x .
     ```
  3. Inyectar en el prompt del drum en lugar del texto genérico.
- Fallback: sin retrieval, prompt actual sin cambios.

**Criterio de aceptación:** un run de estilo funk vs reggaeton produce patrones marcadamente distintos; ambos suenan idiomáticos.

### Fase 7 — Melódicos reciben few-shot

**Qué se hace:**
- En `_system_prompt` para instrumentos no-drum:
  1. Llamar `retrieve_style_examples(header.genre, ..., n=1)` — o cachear por `SongState` si ya lo trajo el Director.
  2. Extraer del ejemplo la parte del **mismo GM role** (bass del example para el bass de la sesión, etc.).
  3. Comprimir 4-8 bars en símbolo (rítmica + contorno melódico + densidad).
  4. Inyectar como bloque "how instruments in this style typically play in this role".
- Cuidar tokens: máximo 1 ejemplo por instrumento, símbolo ≤ 200 tokens.
- Fallback silencioso sin corpus.

**Criterio de aceptación:** bass de reggaeton hace pattern dembow-like, bass de bossa hace pattern bossa-like, con el mismo prompt del usuario cambiando sólo el género.

### Fase 8 — Validador estilístico + eval manual

**Qué se hace:**
- Agregar a `music/validators.py` un check soft (warning, no error): comparar la progresión producida contra la moda del corpus para ese género. Divergencia grande → warning "unusual progression for genre".
- Eval manual: correr 3 prompts (`"reggaeton perreo lento"`, `"bossa nova triste"`, `"90s grunge"`) antes y después de las fases 5-7. Escuchar MIDI, comparar `harmonic_fit`, BPM en rango del corpus, progresión romana cerca de canónica.
- Documentar los resultados en `docs/eval-style-grounding.md`.

**Criterio de aceptación:** eval documentado; el estilo se percibe claramente en los tres prompts.

### Fase 9 (opcional) — MIDI grid concreta en el chord map

**Qué se hace:**
- En `_chord_map_text`, además de los chord tone names, generar la lista de MIDI ints permitidos dentro del range del instrumento. Función `allowed_pitches(chord_symbol, key, midi_range) → {chord_tones, scale_tones, tensions, avoid}` (ints MIDI).
- Formato:
  ```
  bar 3: G7 (chord tones: G, B, D, F)
    for you (range 40-64): chord=[43,47,50,53,55,59,62,64] scale=[+45,+48,+52,+57,+60] avoid=[]
  ```
- Costo: ~30 tokens extra por bar. Beneficio marginal sobre lo que ya hay — hacer sólo si las fases 5-8 no bastan.

### Fase 10 (opcional / v2) — voice-leading + arbiter tools

- `detect_parallels(part_a, part_b)` sobre pares armónicos, wrapper delgado sobre `music21.voiceLeading` → warnings.
- Arbiter con `bind_tools` para consultar `check_voice_leading_between`, `chord_tones_at`, `note_density` en su decisión final.

---

## Orden de PRs

1. **Fase 1** — reader + `note_density` + `detect_overlaps`. Zero behavior change. Chico.
2. **Fase 2** — fetch script + Groove index. Aditivo, chico.
3. **Fase 3** — Lakh index. Aditivo pero pesado (1.6 GB de datos). PR de código chico, corpus fuera de git.
4. **Fase 4** — retrieval module con fallbacks. Chico.
5. **Fase 5** — Director style card. Primer cambio de comportamiento observable.
6. **Fase 6** — drum groove template. **Primer cambio audible marcado.**
7. **Fase 7** — few-shot melódicos.
8. **Fase 8** — eval manual + validador estilístico.
9. **Fase 9** — MIDI grid (si hace falta).
10. **Fase 10** — voice-leading + arbiter tools (v2).
