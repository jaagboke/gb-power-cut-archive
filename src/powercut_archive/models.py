"""The common record that every DNO feed is normalised into.

An OutageRecord is one incident as it looked in one poll of one feed. The
lifecycle engine later compares records across polls to work out what
happened to each incident (new, ETR revised, restored, and so on).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class Status(Enum):
    """Incident status, normalised across DNOs.

    Each DNO uses its own wording; adapters map that wording onto these.
    Anything an adapter doesn't recognise becomes UNKNOWN rather than
    being guessed.
    """

    IN_PROGRESS = "in_progress"
    AWAITING = "awaiting"
    RESTORED = "restored"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OutageRecord:
    dno: str
    source_id: str
    polled_at: datetime
    planned: bool
    status: Status
    category: str | None = None
    voltage: str | None = None
    customers_off: int | None = None
    customers_restored: int | None = None
    reported_at: datetime | None = None
    etr: datetime | None = None
    restored_at: datetime | None = None
    postcode: str | None = None
    lat: float | None = None
    lon: float | None = None
    # The untouched source record, kept so we can re-derive everything if a
    # mapping turns out to be wrong later. compare=False so two polls of the
    # same incident aren't treated as different just because the raw payload
    # carries something we don't use (like the feed's upload timestamp).
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.dno:
            raise ValueError("dno must not be empty")
        if not self.source_id:
            raise ValueError("source_id must not be empty")

        # Every datetime must be timezone-aware UTC. DNO feeds mix GMT, BST
        # and unlabelled local time; normalising to UTC in the adapter (and
        # refusing anything else here) is what stops clock changes producing
        # outages that are an hour out or end before they start.
        for name in ("polled_at", "reported_at", "etr", "restored_at"):
            value = getattr(self, name)
            if value is None:
                continue
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware, got naive {value!r}")
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must be in UTC, got offset {value.utcoffset()}")

        for name in ("customers_off", "customers_restored"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative, got {value}")

    @property
    def key(self) -> tuple[str, str]:
        """Natural key used to match the same incident across polls."""
        return (self.dno, self.source_id)
