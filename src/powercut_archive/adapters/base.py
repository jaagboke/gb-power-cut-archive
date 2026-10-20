from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")


@dataclass
class ParseResult:
    records: list = field(default_factory=list)
    errors: list = field(default_factory=list)  # list of (row, error message)


class Adapter(ABC):
    dno = None
    url = None

    def parse(self, payload, polled_at):
        result = ParseResult()
        for row in self.get_rows(payload):
            try:
                result.records.append(self.parse_row(row, polled_at))
            except (ValueError, KeyError, TypeError) as e:
                # one bad row shouldn't lose us the rest of the poll
                result.errors.append((row, str(e)))
        return result

    @abstractmethod
    def get_rows(self, payload):
        """Return the list of incident rows from the raw response."""

    @abstractmethod
    def parse_row(self, row, polled_at):
        """Convert one row into an OutageRecord."""


def clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def to_int(value):
    value = clean(value)
    if value is None:
        return None
    number = float(value)  # some feeds send "12.0"
    if not number.is_integer():
        raise ValueError(f"Expected a whole number, got {value!r}")
    return int(number)


def to_float(value):
    value = clean(value)
    return float(value) if value is not None else None


def to_bool(value):
    if isinstance(value, bool):
        return value
    value = clean(value)
    if value is None:
        return None
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False
    raise ValueError(f"Can't convert {value!r} to a bool")


def join_postcodes(postcodes):
    # Sorted and de-duplicated, so a feed reordering its postcodes between
    # polls doesn't look like a change to the incident. Inner whitespace is
    # collapsed because NPG pads short outward codes ("BD6  1BJ").
    cleaned = {" ".join(p.split()) for p in postcodes if clean(p)}
    return ", ".join(sorted(cleaned)) if cleaned else None


def to_utc(value, local_tz=UK_TZ):
    """Parse an ISO timestamp and convert it to UTC.

    If the timestamp has no offset, it's assumed to be in local_tz.
    """
    value = clean(value)
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)