"""The neutral fill: refuse before the model sees weak evidence."""
from .catalogue import Hit

REFUSAL = "The archive has no record that answers this. Fill with a neutral tone; do not invent forms."


def gate(hits: list[Hit], threshold: float) -> bool:
    """True when the best card is strong enough to answer from."""
    return bool(hits) and hits[0].score >= threshold
