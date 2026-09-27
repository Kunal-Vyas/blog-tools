"""The one rule for what counts as "the same word".

The Spark job uses it to write slips, and the searcher uses it to read queries.
If the two ever disagree, a word can be in the index and still be unfindable.
"""
import re
import unicodedata

_WORD = re.compile(r"[^\W_]+")          # runs of letters and digits, in any script
_LIGATURES = str.maketrans({"æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe", "ß": "ss"})


def tokens(text: str) -> list[str]:
    """Lower-case, fold accents and ligatures, split on anything that isn't a letter or digit."""
    folded = unicodedata.normalize("NFKD", text)                         # é becomes e + an accent mark
    folded = "".join(c for c in folded if not unicodedata.combining(c))  # drop the accent marks
    folded = folded.translate(_LIGATURES)                                # æ doesn't decompose: fold by hand
    return _WORD.findall(folded.lower())
