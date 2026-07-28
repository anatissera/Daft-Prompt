"""Tests for root logging setup.

The pipeline already emits per-stage TIMING lines at INFO. They were invisible
in production because nothing configured the root logger — uvicorn only
configures its own. These tests lock in that INFO records from a
``music_assistant.*`` logger actually reach a handler.
"""

from __future__ import annotations

import logging

from music_assistant.observability import configure_logging


def test_info_records_reach_a_handler(caplog):
    configure_logging("INFO")

    with caplog.at_level(logging.INFO, logger="music_assistant.band_agent.pipeline"):
        logging.getLogger("music_assistant.band_agent.pipeline").info(
            "skeleton TIMING attempt %d ok: %.1fs", 1, 12.3
        )

    assert "skeleton TIMING attempt 1 ok: 12.3s" in caplog.text


def test_root_level_follows_the_setting():
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING

    configure_logging("INFO")
    assert logging.getLogger().level == logging.INFO


def test_handler_is_attached_once():
    configure_logging("INFO")
    before = len(logging.getLogger().handlers)

    configure_logging("INFO")

    assert len(logging.getLogger().handlers) == before


def test_unknown_level_falls_back_to_info():
    # A typo in LOG_LEVEL must not silence the app or crash the boot.
    configure_logging("NOT_A_LEVEL")
    assert logging.getLogger().level == logging.INFO
