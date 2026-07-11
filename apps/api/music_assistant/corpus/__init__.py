"""Offline corpus ingestion + runtime retrieval of style exemplars.

`groove_index.py` and `lakh_index.py` are batch scripts that read raw MIDI
files with `music.read_midi` and write parquet indices; `retrieve.py` reads
those parquets and returns compact symbols to prompt-time callers. The LLM
never sees raw MIDI — only the symbolic rows this package emits.
"""
