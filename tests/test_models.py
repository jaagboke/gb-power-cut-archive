from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from powercut_archive.models import OutageRecord, Status

UTC = timezone.utc
BST = timezone(timedelta(hours=1))


def make_record(**overrides) -> OutageRecord:
    fields = dict(
        dno="NGED",
        source_id="INCD-65604-l",
        polled_at=datetime(2026, 10, 19, 13, 0, tzinfo=UTC),
        planned=False,
        status=Status.IN_PROGRESS,
        category="HV OVERHEAD",
        voltage="HV",
        customers_off=309,
        customers_restored=0,
        reported_at=datetime(2026, 10, 19, 12, 2, tzinfo=UTC),
        etr=datetime(2026, 10, 19, 15, 0, tzinfo=UTC),
        postcode="HR3 6",
        raw={"Incident ID": "INCD-65604-l"},
    )
    fields.update(overrides)
    return OutageRecord(**fields)


def test_valid_record_builds_with_expected_key():
    record = make_record()
    assert record.key == ("NGED", "INCD-65604-l")


@pytest.mark.parametrize("field_name", ["polled_at", "reported_at", "etr", "restored_at"])
def test_naive_datetime_is_rejected(field_name):
    with pytest.raises(ValueError, match="timezone-aware"):
        make_record(**{field_name: datetime(2026, 10, 19, 13, 0)})


@pytest.mark.parametrize("field_name", ["polled_at", "reported_at", "etr", "restored_at"])
def test_non_utc_datetime_is_rejected(field_name):
    with pytest.raises(ValueError, match="UTC"):
        make_record(**{field_name: datetime(2026, 10, 19, 14, 0, tzinfo=BST)})


def test_record_is_immutable():
    record = make_record()
    with pytest.raises(FrozenInstanceError):
        record.customers_off = 0


@pytest.mark.parametrize("field_name", ["customers_off", "customers_restored"])
def test_negative_customer_counts_are_rejected(field_name):
    with pytest.raises(ValueError, match="negative"):
        make_record(**{field_name: -1})


@pytest.mark.parametrize("field_name", ["dno", "source_id"])
def test_empty_key_fields_are_rejected(field_name):
    with pytest.raises(ValueError, match="empty"):
        make_record(**{field_name: ""})


def test_optional_fields_can_be_missing():
    record = OutageRecord(
        dno="NPG",
        source_id="123",
        polled_at=datetime(2026, 10, 19, 13, 0, tzinfo=UTC),
        planned=False,
        status=Status.UNKNOWN,
    )
    assert record.etr is None
    assert record.raw == {}


def test_raw_payload_is_ignored_in_equality():
    first = make_record(raw={"Upload Date": "2026-10-19T14:00:00"})
    second = replace(first, raw={"Upload Date": "2026-10-19T14:05:00"})
    assert first == second


def test_changed_etr_makes_records_unequal():
    first = make_record()
    revised = replace(first, etr=datetime(2026, 10, 19, 17, 30, tzinfo=UTC))
    assert first != revised
