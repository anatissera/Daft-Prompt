import json
from pathlib import Path

import pytest

from llm_band.domain.song_state import SongState

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_song() -> SongState:
    data = json.loads((FIXTURES / "sample_songstate.json").read_text())
    return SongState.model_validate(data)
