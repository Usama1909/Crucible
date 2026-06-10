"""
Crucible Core Vocabulary
Four domain-blind nouns.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from enum import Enum

def _now():
    return datetime.now(timezone.utc)

class CandidateStatus(Enum):
    EMBRYO   = "EMBRYO"
    PROVING  = "PROVING"
    PROVEN   = "PROVEN"
    DEGRADED = "DEGRADED"
    RETIRED  = "RETIRED"
    DORMANT  = "DORMANT"

class Verdict(Enum):
    UNPROVEN = "UNPROVEN"
    PROVEN   = "PROVEN"
    REJECTED = "REJECTED"
    DEGRADED = "DEGRADED"


@dataclass
class Candidate:
    name:          str
    adapter:       str
    dna:           Dict[str, Any]
    id:            Optional[int]      = None
    status:        CandidateStatus    = CandidateStatus.EMBRYO
    budget:        float              = 0.0
    spawn_reason:  Optional[str]      = None
    retire_reason: Optional[str]      = None
    born_at:       datetime           = field(default_factory=_now)
    retired_at:    Optional[datetime] = None

@dataclass
class Outcome:
    candidate_id:  int
    action:        Dict[str, Any]
    result_value:  float   # ALREADY net of cost. Do not subtract cost again.
    cost:          float   # recorded for transparency/audit only
    context:       Dict[str, Any]
    is_sealed:     bool             = False
    id:            Optional[int]    = None
    ts:            datetime         = field(default_factory=_now)


@dataclass
class VerdictRecord:
    candidate_id:   int
    verdict:        Verdict
    confidence:     float
    stats:          Dict[str, Any]
    evidence_count: int
    evaluated_at:   datetime      = field(default_factory=_now)
    id:             Optional[int] = None


@dataclass
class Memory:
    dna_signature: str
    adapter:       str
    what_worked:   str
    what_failed:   str
    final_stats:   Dict[str, Any]
    sample_size:   int
    confidence:    float
    context:       Dict[str, Any] = field(default_factory=dict)
    id:            Optional[int] = None
    created_at:    datetime      = field(default_factory=_now)
