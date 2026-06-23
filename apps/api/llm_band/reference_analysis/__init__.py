"""Bounded context for future listening/reference-analysis features.

This package intentionally contains only models, ports, use cases, and fakes for
now. It does not analyze audio, download media, or integrate providers.
"""

from .models import (
    AudioProfile,
    ExplanationAnswer,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
    StemProfile,
)

__all__ = [
    "AudioProfile",
    "ExplanationAnswer",
    "ReferenceProfile",
    "ReferenceSource",
    "SectionProfile",
    "StemProfile",
]
