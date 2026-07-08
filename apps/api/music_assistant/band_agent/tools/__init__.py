from .web_search import search_web
from .corpus import retrieve_corpus, infer_genre_from_titles
from .compose import compose_band
from .drums import synthesize_drum_notes

__all__ = [
    "search_web",
    "retrieve_corpus",
    "infer_genre_from_titles",
    "compose_band",
    "synthesize_drum_notes",
]
