"""
Crucible Gate — Splitter
Train/judge split logic.
Time-ordered data: chronological split only. Never shuffled.
"""
from typing import List, Tuple
from crucible.core.vocabulary import Outcome


def chronological_split(outcomes: List[Outcome],
                         judge_pct: float = 0.3) -> Tuple[List[Outcome], List[Outcome]]:
    """Split time-ordered outcomes into train and sealed judge set.
    The judge set is never touched during candidate selection."""
    if not outcomes:
        return [], []
    n = len(outcomes)
    split = max(1, int(n * (1 - judge_pct)))
    return outcomes[:split], outcomes[split:]


def random_split(outcomes: List[Outcome],
                  judge_pct: float = 0.3) -> Tuple[List[Outcome], List[Outcome]]:
    """For non-time-ordered data only. Uses is_sealed flag if set."""
    sealed = [o for o in outcomes if o.is_sealed]
    unsealed = [o for o in outcomes if not o.is_sealed]
    if sealed:
        return unsealed, sealed
    # Fall back to chronological if no sealed flag set
    return chronological_split(outcomes, judge_pct)