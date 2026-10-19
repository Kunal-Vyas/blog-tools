"""The historian's thesaurus: the restorer's words -> the archive's words.

Archives keep controlled vocabularies (the Getty Art & Architecture Thesaurus
is the art-world one) so different words for the same thing reach the same
records. This is the studio's own, small and hand-written. Embeddings are the
learned version of it.
"""
import re

TERMS = {
    r"\b(hole|gap|missing|damaged area)\b": "lacuna loss",
    r"\b(flaking|peeling|coming off)\b": "lifting",
    r"\bscales\b": "balance",
    r"\b(sketch|study)\b": "drawing disegno",
    r"\bunderdrawing\b": "sinopia infrared",
    r"\b(gold|gilt)\b": "gilded leaf",
    r"\bblue\b": "azurite ultramarine",
    r"\bred\b": "vermilion lake",
    r"\b(old|historic) photo\w*\b": "photograph 1931",
    r"\b(painter|artist)\b": "jacopo",
    r"\bpaid\b": "florins payment",
    r"\bwhite (crust|bloom|deposits?)\b": "efflorescence salts",
}


def expand(query: str) -> str:
    extra = [words for pattern, words in TERMS.items() if re.search(pattern, query.lower())]
    return query + (" " + " ".join(extra) if extra else "")
