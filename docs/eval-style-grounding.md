# Style Grounding — eval manual

Este documento captura el procedimiento (y a futuro, resultados) del eval manual de las Fases 5-8 del plan `plans/style-grounding.md`.

## Setup

1. Descargar los corpora una vez:

   ```bash
   cd apps/api
   python -m scripts.fetch_corpora --groove   # ~5 MB, rápido
   python -m scripts.fetch_corpora --lakh     # ~1.6 GB, ~10 min
   ```

2. Indexar (batch, corre una vez):

   ```bash
   cd apps/api
   python -m music_assistant.corpus.groove_index
   python -m music_assistant.corpus.lakh_index --workers 8
   ```

Los índices quedan en `apps/api/data/index/` (parquet si `pyarrow` está instalado, JSONL si no). Ambos están en `.gitignore`.

Si `data/` no existe, el pipeline **degrada al comportamiento anterior sin errores** — todos los retrievals devuelven listas vacías / `None`.

## Prompts de eval

Correr los siguientes prompts en el web UI (`http://localhost:3000`) y guardar los MIDIs generados en `docs/eval/samples/`:

1. `"reggaeton perreo lento"` — se espera BPM ~88-96, mode minor, groove dembow, progresión tipo i-VI-III-VII.
2. `"bossa nova triste"` — se espera BPM ~80-100, jazz-oriented, guitarra + bass acompañamiento sincopado.
3. `"90s grunge"` — se espera BPM ~110-130, key minor, guitarra distorsionada, drums four-on-the-floor + snare backbeat fuerte.

## Métricas a observar

Por cada prompt, comparar antes/después de habilitar el corpus:

- **`harmonic_fit`** (ya reportado por API): fracción de notas evaluables que son chord tones. Objetivo: mantener o subir.
- **Progresión emitida** — chequear si aparecen las progresiones canónicas del corpus (spot-check contra `retrieve_style_examples`).
- **BPM emitido** — dentro del rango del corpus para ese género.
- **Warnings de validator** — `unusual_progression_for_genre` debe ser raro cuando el estilo matchea el corpus.
- **Audio** — escuchar. El drum de reggaeton vs grunge debe sonar marcadamente distinto sin ambigüedad.

## Cómo comparar sin el corpus

Renombrar la carpeta `apps/api/data/index/` para forzar el fallback:

```bash
mv apps/api/data/index apps/api/data/index.disabled
# correr el prompt
mv apps/api/data/index.disabled apps/api/data/index
```

El log del backend no debe mostrar cambios de código path, sólo prompts más chicos.

## Resultados

_(rellenar tras correr el eval)_
