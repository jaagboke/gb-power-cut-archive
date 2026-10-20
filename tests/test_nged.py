import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from powercut_archive.adapters.nged import NGEDAdapter
from powercut_archive.models import Status

FIXTURE = Path(__file__).parent / "fixtures" / "nged_20261019T2120.json"
# The fixture was saved at 21:20 BST
POLLED_AT = datetime(2026, 10, 19, 20, 20, tzinfo=timezone.utc)
UTC = timezone.utc


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def parse(payload):
    return NGEDAdapter().parse(payload, POLLED_AT)


def by_id(result):
    return {r.source_id: r for r in result.records}


def test_whole_sample_parses_without_errors(payload):
    result = parse(payload)
    assert result.errors == []
    assert len(result.records) == 21


def test_record_keys_are_unique(payload):
    keys = [r.key for r in parse(payload).records]
    assert len(keys) == len(set(keys))


def test_unplanned_fault_maps_all_fields(payload):
    record = by_id(parse(payload))["INCD-108752-l"]
    assert record.dno == "NGED"
    assert record.planned is False
    assert record.status == Status.IN_PROGRESS
    assert record.category == "HV OVERHEAD"
    assert record.voltage == "HV"
    assert record.customers_off == 14
    assert record.customers_predicted_off == 0
    assert record.customers_restored == 0
    # BST times, one hour ahead of UTC
    assert record.reported_at == datetime(2026, 10, 19, 14, 6, tzinfo=UTC)
    assert record.etr == datetime(2026, 10, 20, 1, 0, tzinfo=UTC)
    assert record.restored_at is None
    assert record.postcode == "TA7 0JF, TA7 0JG"
    assert record.lat == 51.1192
    assert record.lon == -2.988763


def test_raw_is_the_untouched_row(payload):
    original = copy.deepcopy(payload["result"]["records"][0])
    record = parse(payload).records[0]
    assert record.raw == original


def test_no_timestamp_is_after_the_poll(payload):
    # A timezone mistake would push the newest faults into the future
    for record in parse(payload).records:
        assert record.reported_at <= POLLED_AT


def test_planned_work_falls_back_to_planned_end_for_etr(payload):
    record = by_id(parse(payload))["INCD-24551-t"]
    assert record.planned is True
    assert record.raw["etr"] is None
    assert record.etr == datetime(2026, 10, 20, 19, 0, tzinfo=UTC)


def test_etr_wins_over_planned_end_when_both_present(payload):
    row = next(r for r in payload["result"]["records"] if r["fault_id"] == "INCD-24551-t")
    row["etr"] = "2026-10-20T12:00:00"
    record = by_id(parse(payload))["INCD-24551-t"]
    assert record.etr == datetime(2026, 10, 20, 11, 0, tzinfo=UTC)


def test_postcodes_are_sorted(payload):
    record = by_id(parse(payload))["INCD-24551-t"]
    assert record.raw["postcode"] == "TA9 3PL, TA7 8FF"
    assert record.postcode == "TA7 8FF, TA9 3PL"


def test_awaiting_status(payload):
    assert by_id(parse(payload))["INCD-140462-h"].status == Status.AWAITING


@pytest.mark.parametrize("value", ["Restored", "", None])
def test_unrecognised_status_is_unknown(payload, value):
    payload["result"]["records"][0]["status"] = value
    assert parse(payload).records[0].status == Status.UNKNOWN


def test_winter_time_is_treated_as_gmt(payload):
    # Europe/London, not a fixed +1: after the clocks go back, local == UTC
    payload["result"]["records"][0]["date_of_reported_fault"] = "2026-12-01T10:00:00"
    record = parse(payload).records[0]
    assert record.reported_at == datetime(2026, 12, 1, 10, 0, tzinfo=UTC)


def test_bad_row_is_collected_without_losing_the_rest(payload):
    payload["result"]["records"][0]["confirmed_off"] = "lots"
    result = parse(payload)
    assert len(result.records) == 20
    assert len(result.errors) == 1


def test_failed_response_is_rejected(payload):
    payload["success"] = False
    with pytest.raises(ValueError, match="success"):
        parse(payload)
