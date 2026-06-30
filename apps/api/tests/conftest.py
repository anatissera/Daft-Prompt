import json
from pathlib import Path

import pytest

from music_assistant.domain.song_state import SongState

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_song() -> SongState:
    data = json.loads((FIXTURES / "sample_songstate.json").read_text())
    return SongState.model_validate(data)
