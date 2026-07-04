# Playback Limitations

LLMinem treats playback as an inspection aid for symbolic composition.

Current playback/export expectations:

- Generated `SongState` remains the source of truth.
- MIDI and MusicXML exports are render artifacts, not canonical state.
- The frontend mixer is meant for play/stop, mute, solo, and quick inspection.
- General MIDI and browser sample playback can make a reasonable symbolic part
  sound less realistic than intended.
- Timbre traits in `CompositionBrief` guide arrangement and instrumentation even
  when playback can only approximate them.

Deferred until playback blocks composition evaluation:

- production-grade mixing;
- realistic synth programming;
- custom sample libraries;
- DAW-like editing;
- mastering or loudness workflows.
