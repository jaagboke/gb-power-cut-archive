from powercut_archive.adapters.base import (
    Adapter,
    clean,
    join_postcodes,
    to_bool,
    to_float,
    to_int,
    to_utc,
)
from powercut_archive.models import OutageRecord, Status

STATUSES = {
    "in progress": Status.IN_PROGRESS,
    "awaiting": Status.AWAITING,
}


class NGEDAdapter(Adapter):
    dno = "NGED"
    url = (
        "https://connecteddata.nationalgrid.co.uk/api/3/action/datastore_search"
        "?resource_id=a1365982-4e05-463c-8304-8323a2ba0ccd&limit=1000"
    )

    def get_rows(self, payload):
        if not payload.get("success"):
            raise ValueError("NGED response has success=false")
        return payload["result"]["records"]

    def parse_row(self, row, polled_at):
        planned = to_bool(row["planned"])
        if planned is None:
            raise ValueError("planned is blank")

        status = clean(row["status"])
        status = STATUSES.get(status.lower(), Status.UNKNOWN) if status else Status.UNKNOWN

        # Naive timestamps are UK local time (checked against real polls), which
        # is what to_utc assumes by default. NGED leaves etr empty for planned
        # work, so fall back to the planned end time it gives customers.
        etr = to_utc(row["etr"])
        if etr is None:
            etr = to_utc(row["planned_outage_end_date"])

        postcode = row["postcode"]
        postcodes = postcode.split(",") if postcode else []

        return OutageRecord(
            dno=self.dno,
            source_id=clean(row["fault_id"]),
            polled_at=polled_at,
            planned=planned,
            status=status,
            category=clean(row["category"]),
            voltage=clean(row["voltage"]),
            customers_off=to_int(row["confirmed_off"]),
            customers_predicted_off=to_int(row["predicted_off"]),
            customers_restored=to_int(row["restored"]),
            reported_at=to_utc(row["date_of_reported_fault"]),
            etr=etr,
            restored_at=to_utc(row["date_of_restoration"]),
            postcode=join_postcodes(postcodes),
            lat=to_float(row["location_latitude"]),
            lon=to_float(row["location_longitude"]),
            raw=row,
        )
