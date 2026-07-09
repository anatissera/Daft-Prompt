from music_assistant.infrastructure.mir.basic_pitch_transcriber import quantize_notes


def test_quantize_notes_maps_seconds_to_bar_grid():
    notes = quantize_notes([(0.5, 1.0, 60, 100), (2.1, 2.4, 64, 200)])
    assert [(note.bar, note.start_beat, note.pitch, note.velocity) for note in notes] == [(0, 1.0, 60, 100), (1, 0.2, 64, 127)]
