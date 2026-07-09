"""Optional Basic Pitch adapter; imports the model runtime only on use."""
from __future__ import annotations
from pathlib import Path
from music_assistant.domain.song_state import Note


class BasicPitchUnavailable(RuntimeError):
    pass


class BasicPitchTranscriber:
    def transcribe_melody(self, source):
        path = _source_path(source.uri)
        try:
            from basic_pitch.inference import predict
        except ImportError as exc:
            raise BasicPitchUnavailable("Install music-assistant[transcription] to enable Basic Pitch transcription.") from exc
        _model_output, midi_data, _note_events = predict(str(path))
        notes = []
        for instrument in midi_data.instruments:
            for item in instrument.notes:
                notes.append((item.start, item.end, item.pitch, item.velocity))
        return quantize_notes(notes)


def quantize_notes(events, *, tempo_bpm: float = 120.0, beats_per_bar: float = 4.0):
    seconds_per_beat = 60.0 / tempo_bpm
    result = []
    for start, end, pitch, velocity in events:
        beat = max(0.0, start / seconds_per_beat)
        duration = max(0.125, (end - start) / seconds_per_beat)
        bar = int(beat // beats_per_bar)
        result.append(Note(bar=bar, start_beat=round(beat % beats_per_bar, 3), pitch=int(pitch), dur=round(duration, 3), velocity=max(1, min(127, int(velocity)))))
    return result


def _source_path(uri: str) -> Path:
    value = uri.removeprefix("file://").removeprefix("local://")
    path = Path(value)
    if not path.is_file():
        raise FileNotFoundError(f"Transcription source is unavailable: {uri}")
    return path
