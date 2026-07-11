# Idea: timbres arbitrarios vía parámetros de síntesis emitidos por el LLM

## Contexto

Hoy el director elige instrumentos de una **paleta cerrada** (`apps/api/music_assistant/domain/patch.py`): ~80 patches sampleados (GM/SF3) + 6 presets de síntesis nativa en Tone.js (`supersaw_lead`, `sub_bass`, `pluck`, `warm_pad`, `vocal_fx`, `wobble_bass`).
La paleta cerrada existe por buenas razones: todo patch es renderizable garantizado, la validación es a nivel schema (`Patch` es un `Literal` de pydantic), y el modo de falla es ruidoso (se dropea el instrumento) en vez de inaudible (timbre incorrecto que suena).

El costo es un **techo tímbrico**: géneros cuyo sonido definitorio es un timbre sintético que MIDI no puede transportar (un acid 303, un growl FM de riddim, un reese de DnB) chocan contra la aproximación GM plana hasta que alguien construye el preset a mano (~30 líneas en `nativeSynthLayer.ts`, como se hizo con `wobble_bass`).

## La idea

En vez de que el modelo **nombre** un instrumento, que emita **parámetros de síntesis** en un schema validado, y Tone.js construye el synth en el frontend:

```python
class SynthDesign(BaseModel):
    oscillators: list[OscSpec]      # type: saw/square/sine/triangle/fm, detune, count, mix
    amp_envelope: ADSR              # attack/decay/sustain/release, rangos acotados
    filter: FilterSpec              # type, cutoff, Q, envelope amount
    filter_lfo: LFOSpec | None      # rate (o división rítmica sync al tempo), depth, shape
    effects: list[EffectSpec]       # distortion/chorus/reverb, cantidades acotadas
```

Esto da **timbres genuinamente arbitrarios manteniendo la garantía de renderizado**: el LLM diseña el sonido, pero solo dentro de un espacio de parámetros que siempre produce audio válido.

## Por qué es la evolución correcta de la paleta cerrada

- Conserva la propiedad clave: la restricción es sobre el *renderizado*, no sobre la *decisión musical*.
- Los errores siguen siendo ruidosos: un parámetro fuera de rango falla la validación pydantic, no suena mal en silencio.
- El conocimiento del LLM sobre sound design ("un reese son dos saws detuneados con lowpass en movimiento") pasa a ser utilizable directamente.
- Los 6 presets actuales se vuelven simplemente *defaults con nombre* dentro del mismo espacio de parámetros.

## Alcance (proyecto mediano)

1. **Schema + validación de rangos** para que no genere basura inaudible:
   cutoffs dentro de rango audible, ADSR con mínimos audibles, ganancias acotadas para evitar clipping, LFO rates razonables (mejor: divisiones rítmicas sync al tempo en vez de Hz libres).
2. **Factory en el frontend**: `SynthDesign → nodo Tone.js`, generalización de `NativeSynthLayer.createTrack`. Los 5-6 makers actuales son la referencia de qué primitivas hacen falta.
3. **Prompt del skeleton**: el roster puede llevar `synth_design` opcional en vez de (o además de) `patch`; hay que decidir cuándo el director diseña vs. cuándo samplea.
4. **Export offline**: el MP3 hoy renderiza vía spessasynth/SF3 con aproximaciones GM para los presets nativos. Con synths custom hace falta render offline del grafo Tone.js (`Tone.Offline`) y mezclarlo con el render SF3 — es la parte más laboriosa.
5. **MIDI export**: sigue siendo aproximación GM (un .mid no puede transportar el diseño); opcionalmente exportar el `SynthDesign` como JSON sidecar.
6. **Guardrails de calidad**: un paso barato de sanity (¿RMS audible? ¿no clipea?) o un critic-pass del propio LLM sobre el diseño antes de aceptarlo.

## Riesgos conocidos

- Calidad variable: el LLM puede diseñar timbres válidos pero mediocres; los presets curados son un piso de calidad que esto pierde.
- Presión de tokens: un `SynthDesign` por instrumento agranda la salida del skeleton (mitigable: solo diseñar para 1-2 instrumentos "protagonistas" y usar paleta para el resto).
- Reproducibilidad: dos corridas del mismo prompt darán timbres distintos (feature o bug según el caso).

## Disparador para hacerlo

Cuando el techo tímbrico moleste en serio: si la lista de "presets que faltan" (303, reese, growl FM, etc.) empieza a crecer más rápido de lo que vale la pena mantenerla a mano.
