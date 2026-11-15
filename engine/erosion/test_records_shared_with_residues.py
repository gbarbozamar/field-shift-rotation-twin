"""Guard of decision D164 of issue #77, which amends D158.

D158 takes the records of the computed C out of the catalogue the service
loads (``params/records/``). D164 corrects it: six of those records are also
read by the residue ledger, EP4 (``engine/residues/ledger.py``), for the
aboveground residue at harvest: ``rusle2_residue_yield_ratio`` and
``rusle2_crop_yield`` of soybean, wheat and maize. Those six stay in the
catalogue, under ``params/records/residues/``; the other 61 are in
``params/withdrawn/computed_c/``.

These tests hold that with the catalogue the service loads:

- the six records are there, and none of them is among the withdrawn ones;
- the residue ledger of both rotations of D128, in every phase, is the ledger
  EP4 gives with the whole set of records that ``params/records/`` held before
  D158 (the catalogue plus the withdrawn records), value for value and reason
  for reason;
- without the six, the aboveground residue of every crop is missing: the case
  D164 describes, which no test caught.

Unit l0/computed-c-out-of-catalogue (issue #270). PROPOSED cases (blueprint
section 3.7). The file is in ``engine/erosion/`` because that unit owns the
tests that load these records and does not own ``engine/residues/`` (lane L1);
its place is PROPOSED.

Every date here is a PLACEHOLDER date, not a date of D72: no crop spans the
first day of the agricultural year, so no cycle is laid out before the first
one. No expected value of the science is written: each number is computed
again here from the records.

Run from the repository root:
``py -3.12 -m pytest engine/erosion/test_records_shared_with_residues.py``.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from contracts.inputs.site_climate import SiteClimate
from contracts.residue_ledger import ResidueLedger
from contracts.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.calendar.repeat import list_phases, phase_calendar
from engine.residues import build_residue_ledger
from params.catalogue import check_catalogue, identity, load_folder, read_value

ROOT = Path(__file__).parent.parent.parent
RECORDS = ROOT / "params" / "records"
WITHDRAWN_C_RECORDS = ROOT / "params" / "withdrawn" / "computed_c"

# The two records EP4 reads by crop for the aboveground residue at harvest
# (D129 (c): residue/yield ratio times yield), and the crops of D128.
RATIO_ID = "rusle2_residue_yield_ratio"
YIELD_ID = "rusle2_crop_yield"
SHARED_IDS = (RATIO_ID, YIELD_ID)
CROPS = ("soybean", "wheat", "maize")

MARK = "PLACEHOLDER"
IDS = {"case_id": "test-case", "field_id": "test-field"}
LABEL = {"provenance": "DECLARED", "source": f"{MARK}: test date"}
START_MONTH = 7  # PLACEHOLDER start month of the agricultural year
RECORD_START = dt.date(2001, 7, 1)  # PLACEHOLDER record: four whole years
RECORD_END = dt.date(2005, 6, 30)

# The rotations of D128 on PLACEHOLDER dates: (crop, sowing, harvest).
ROTATIONS: dict[str, list[tuple[str, str, str]]] = {
    "soybean-winter-fallow": [("soybean", "2001-11-01", "2002-04-30")],
    "soybean-wheat-maize": [
        ("wheat", "2001-07-10", "2001-11-30"),
        ("soybean", "2001-12-10", "2002-05-10"),
        ("maize", "2002-09-10", "2003-04-10"),
    ],
}


def rotation(name: str) -> RotationDefinition:
    gone = {"missing": {"reason": "NOT_DECLARED"}}
    return RotationDefinition.model_validate(
        {
            "contract": "rotation_definition",
            "example_data": True,
            **IDS,
            "rotation_id": name,
            "label": f"{MARK} rotation",
            "ag_year_start": {"month": START_MONTH, "provisional": True, **LABEL},
            "repeats": True,
            "components": [
                {
                    "component_id": f"c{position}",
                    "position": position,
                    "crop_id": crop,
                    "purpose": "grain",
                    "sowing": {"date": sowing, **LABEL},
                    "harvest": {"date": harvest, **LABEL},
                    "management": {
                        "residue": "left_on_surface",
                        "grazing": gone,
                        "termination": gone,
                    },
                }
                for position, (crop, sowing, harvest) in enumerate(
                    ROTATIONS[name], start=1
                )
            ],
        }
    )


def climate() -> SiteClimate:
    days = []
    day = RECORD_START
    while day <= RECORD_END:
        days.append({"date": day.isoformat(), "value": 1.0})
        day += dt.timedelta(days=1)
    gone = {
        "value": None,
        "unit": f"{MARK}_unit",
        "missing": {"reason": "NOT_DECLARED"},
    }
    return SiteClimate.model_validate(
        {
            "contract": "site_data_climate",
            "example_data": True,
            **IDS,
            "point": {"latitude": gone, "longitude": gone, "elevation": gone},
            "daily_series": [
                {
                    "quantity": "test_quantity",
                    "unit": f"{MARK}_unit",
                    "provenance": "OBSERVED",
                    "source": f"{MARK}: test series",
                    "range_missing": {"reason": "NOT_AVAILABLE"},
                    "time_zone": "UTC",
                    "start_date": RECORD_START.isoformat(),
                    "end_date": RECORD_END.isoformat(),
                    "days": days,
                }
            ],
            "monthly_series": [],
        }
    )


def service_catalogue() -> dict[str, dict]:
    """The catalogue the service loads: every record under params/records/,
    as ``load_folder`` returns it (api/config.py), loaded and checked."""
    records, problems = load_folder(RECORDS)
    assert problems == [] and check_catalogue(records) == []
    return records


def withdrawn_c_records() -> dict[str, dict]:
    """The records of params/withdrawn/computed_c/, loaded by the path of that
    folder and checked, keyed from params/."""
    records, problems = load_folder(WITHDRAWN_C_RECORDS)
    assert problems == [] and check_catalogue(records) == []
    return {f"withdrawn/computed_c/{name}": r for name, r in records.items()}


def shared(records: dict[str, dict]) -> dict[tuple[str, str], dict]:
    """The records with one of the two identifiers and a crop scope, by
    identifier and crop."""
    found: dict[tuple[str, str], dict] = {}
    for record in records.values():
        if record["id"] in SHARED_IDS and set(record["scope"]) == {"crop"}:
            key = (record["id"], record["scope"]["crop"])
            assert key not in found, key
            found[key] = record
    return found


def ledgers(parameters: dict[str, dict]) -> dict[tuple[str, int], ResidueLedger]:
    """EP4 for both rotations of D128 and every phase (D109, D141)."""
    climate_ = climate()
    result = {}
    for name in ROTATIONS:
        definition = rotation(name)
        calendar = build_rotation_calendar(definition)
        assert calendar.feasibility.feasible, name
        for phase in list_phases(calendar):
            result[(name, phase)] = build_residue_ledger(
                definition,
                phase_calendar(calendar, phase),
                climate_,
                parameters=parameters,
            )
    # A one-year rotation has one phase; the other has one per year (D109).
    assert sorted(result) == [
        ("soybean-wheat-maize", 0),
        ("soybean-wheat-maize", 1),
        ("soybean-winter-fallow", 0),
    ]
    return result


def dumped(ledger: ResidueLedger) -> dict[str, Any]:
    return ledger.model_dump(mode="json")


def test_service_catalogue_holds_the_six_records_the_residue_ledger_reads():
    """D164: the two records EP4 reads for each crop of D128 are in the
    catalogue the service loads, each with a value, and no withdrawn record
    has their identifier or the identity of any record of the catalogue."""
    service, withdrawn = service_catalogue(), withdrawn_c_records()
    found = shared(service)
    assert sorted(found) == sorted((pid, crop) for pid in SHARED_IDS for crop in CROPS)
    for key, record in found.items():
        assert isinstance(read_value(record), float), key
    assert shared(withdrawn) == {}
    assert not {r["id"] for r in withdrawn.values()} & set(SHARED_IDS)
    loaded = {identity(record) for record in service.values()}
    for name, record in withdrawn.items():
        assert identity(record) not in loaded, name


def test_residue_ledger_with_the_service_catalogue_is_the_ledger_of_the_whole_set():
    """D164: with the catalogue the service loads, the residue ledger of both
    rotations of D128, in every phase, is the ledger EP4 gives with the
    catalogue plus the withdrawn records (the set params/records/ held before
    D158): the same document, value for value and reason for reason. The
    aboveground residue of every entry is a number, the residue/yield ratio
    times the yield of its crop, computed again here from the two records."""
    service, withdrawn = service_catalogue(), withdrawn_c_records()
    assert set(service).isdisjoint(withdrawn)
    whole = {**service, **withdrawn}
    assert check_catalogue(whole) == []
    records = shared(service)
    with_service, with_whole = ledgers(service), ledgers(whole)
    seen = set()
    for key, ledger in with_service.items():
        assert dumped(ledger) == dumped(with_whole[key]), key
        assert ledger.components, key
        for entry in ledger.components:
            where = (key, entry.component_id, entry.cycle)
            ratio = read_value(records[(RATIO_ID, entry.crop_id)])
            crop_yield = read_value(records[(YIELD_ID, entry.crop_id)])
            produced = entry.aboveground_mass_produced
            assert produced.missing is None, (where, produced.missing)
            assert produced.value == ratio * crop_yield, where
            # The residue is declared left on the surface: all of it is retained.
            assert entry.aboveground_mass_retained.value == produced.value, where
            seen.add(entry.crop_id)
    assert seen == set(CROPS)


def test_without_the_six_records_the_residue_ledger_loses_the_aboveground_residue():
    """What D164 prevents: with the six records taken out of the catalogue,
    the aboveground residue of every entry of every crop is missing
    (MISSING_INPUT), naming the two records with D56. So the test above
    fails if they leave the catalogue again."""
    service = service_catalogue()
    without = {
        name: record
        for name, record in service.items()
        if record["id"] not in SHARED_IDS
    }
    assert len(service) - len(without) == len(SHARED_IDS) * len(CROPS)
    with_service = ledgers(service)
    for key, ledger in ledgers(without).items():
        assert dumped(ledger) != dumped(with_service[key]), key
        assert ledger.components, key
        for entry in ledger.components:
            where = (key, entry.component_id, entry.cycle)
            for value in (
                entry.aboveground_mass_produced,
                entry.aboveground_mass_retained,
            ):
                assert value.value is None, where
                assert value.missing is not None, where
                assert value.missing.reason == "MISSING_INPUT", where
            detail = entry.aboveground_mass_produced.missing.detail
            for pid in SHARED_IDS:
                assert f"parameter '{pid}' with scope" in detail, where
            assert "no record in parameters (D56)" in detail, where
