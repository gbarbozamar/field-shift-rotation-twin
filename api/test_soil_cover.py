"""Acceptance tests of the monthly soil cover of RothC (D222 of #77; unit
l2/rothc-soil-cover-d222, brief #373).

Run with ``uv run pytest api/test_soil_cover.py`` from the repository root.

D222: quantity ``soil_cover_state``, unit ``dimensionless``, 1.0 when a living
crop of the repeated calendar stands on most days of the month, 0.0
otherwise, including the fallow under residue; "most days" is read as more
than half, so an exactly half month is 0.0. The runner counts the days with
a live crop by month with lane L1's public rule
``engine.water.living_crop.live_crop_by_day`` (D135, D136, the window of
D157); the producer applies the rule to the counts.

EXAMPLE DATA. Every date is PLACEHOLDER: the years mean nothing. The climate
is the PLACEHOLDER chain example (one agricultural year from 2001-07-01, start
month 7). The catalogue is the repository's (``params/records/``), as the
service loads it; the hand-made calendars use the crop ``soybean`` only on
periods shorter than the sum of its four stage lengths, read from that
catalogue, so every day of such a period has a live crop (D135, the stages
cut at the harvest). No value of the method is written here.

Status: PROPOSED test cases (blueprint section 3.7).
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from api import carbon_forcing as producer
from api import engines as runner
from api.carbon_forcing import LiveCropMonth, build_carbon_forcing
from api.engines import (
    EngineFunctions,
    EntryPointEngines,
    discover_engine_functions,
    live_crop_months_for_forcing,
)
from api.test_engines import (
    CALENDAR_DOCUMENT,
    CARBON_MODELS,
    ROTATION,
    Fake,
    balance,
    chain_climate,
    climate_result,
    fakes,
    soil_result,
)
from contracts.carbon_forcing import CarbonForcing
from contracts.inputs import RotationCalendar, SiteClimate
from contracts.results.models import Missing

ROOT = Path(__file__).parent.parent
SOURCE = "PLACEHOLDER: hand-written date of a test, not a declaration"
CROP = "soybean"  # a crop word of the catalogue (D128)
NO_RECORDS = "placeholder_crop_without_records"  # no stage length in the catalogue


def repository_catalogue() -> dict[str, dict]:
    from params.catalogue import load_folder

    records, problems = load_folder(ROOT / "params" / "records")
    assert problems == [], problems
    return records


def stage_total(parameters: dict[str, dict], crop: str) -> float:
    """The sum of the four FAO-56 stage lengths of ``crop`` in the catalogue."""
    lengths = [
        record["value"]
        for record in parameters.values()
        if record["id"].startswith("fao56_stage_length_")
        and record["scope"] == {"crop": crop}
    ]
    assert len(lengths) == 4, lengths
    return float(sum(lengths))


def date_value(day: str) -> dict[str, Any]:
    return {"date": day, "provenance": "DECLARED", "source": SOURCE}


def hand_calendar(components: list[tuple[str, str, str]]) -> RotationCalendar:
    """A one-year calendar over the chain record, start month 7, under the
    identifiers of the runner's tests: (crop, sowing, harvest) per component."""
    document = copy.deepcopy(CALENDAR_DOCUMENT)
    document["start_date"], document["end_date"] = "2001-07-01", "2002-06-30"
    document["ag_year_start"]["month"] = 7
    document["feasibility"] = {"feasible": True, "violations": []}
    document["components"] = [
        {
            "component_id": f"PLACEHOLDER-component-{position}",
            "crop_id": crop,
            "start": date_value(sowing),
            "end": date_value(harvest),
            "periods": [],
        }
        for position, (crop, sowing, harvest) in enumerate(components, start=1)
    ]
    return RotationCalendar.model_validate(document)


# The hand-made calendar of the cases (PLACEHOLDER dates):
# - July 2001: 16 of 31 days live, just over half -> 1.0;
# - August 2001: fallow -> 0.0;
# - September 2001: 15 of 30 days live, exactly half -> 0.0;
# - October 2001: 12 of 31 live (sown on the 20th) -> 0.0;
# - November 2001: every day live -> 1.0;
# - December 2001: harvest on the 20th, 20 of 31 live, a month crossing a
#   harvest -> 1.0;
# - January 2002: fallow -> 0.0;
# - February 2002: a crop with no stage length in the catalogue -> missing;
# - March to June 2002: fallow -> 0.0.
CASES = [
    (CROP, "2001-07-01", "2001-07-16"),
    (CROP, "2001-09-01", "2001-09-15"),
    (CROP, "2001-10-20", "2001-12-20"),
    (NO_RECORDS, "2002-02-01", "2002-02-28"),
]
EXPECTED: dict[tuple[int, int], float | None] = {
    (2001, 7): 1.0,
    (2001, 8): 0.0,
    (2001, 9): 0.0,
    (2001, 10): 0.0,
    (2001, 11): 1.0,
    (2001, 12): 1.0,
    (2002, 1): 0.0,
    (2002, 2): None,
    (2002, 3): 0.0,
    (2002, 4): 0.0,
    (2002, 5): 0.0,
    (2002, 6): 0.0,
}
EXPECTED_LIVE_DAYS = {
    (2001, 7): (16, 31),
    (2001, 8): (0, 31),
    (2001, 9): (15, 30),
    (2001, 10): (12, 31),
    (2001, 11): (30, 30),
    (2001, 12): (20, 31),
    (2002, 1): (0, 31),
}


def live_crop_by_day():
    found = discover_engine_functions().live_crop_by_day
    if found is None:
        pytest.skip("engine.water.living_crop.live_crop_by_day is not built")
    return found


def cover_of(forcing: CarbonForcing) -> dict[tuple[int, int], Any]:
    (series,) = forcing.soil_cover
    return {(item.year, item.month): item for item in series.months}


def run_rothc_on(
    calendar_: RotationCalendar,
    *,
    climate: SiteClimate | None = None,
    live: Any = "discover",
    parameters: dict[str, dict] | None = None,
) -> tuple[CarbonForcing, Fake]:
    """The runner on fakes of EP1, EP2 and EP3 and a fake EP6; the forcing EP6 got."""
    calendar_fn, soil_fn, water_fn = fakes(calendar_answer=calendar_)
    rothc = Fake(balance(carbon_model="rothc"))
    engines = EntryPointEngines(
        EngineFunctions(
            build_rotation_calendar=calendar_fn,
            compute_soil_loss=soil_fn,
            compute_water_deficit_exposure=water_fn,
            run_rothc=rothc,
            live_crop_by_day=live_crop_by_day() if live == "discover" else live,
        ),
        carbon_models=CARBON_MODELS,
        parameters=parameters if parameters is not None else repository_catalogue(),
    )
    engines.run(ROTATION, climate_result(climate or chain_climate()), soil_result())
    ((forcing,), _) = rothc.calls[0]
    assert isinstance(forcing, CarbonForcing)
    return forcing, water_fn


# --- 1. the producer: the rule on the counts ---------------------------------------


def producer_forcing(live_crop_months: Any) -> CarbonForcing:
    calendar_ = hand_calendar(CASES)
    built = build_carbon_forcing(
        calendar_,
        chain_climate(),
        soil_result().data,
        live_crop_months=live_crop_months,
    )
    assert isinstance(built, CarbonForcing), built
    return built


def counts(**changes: Any) -> dict[tuple[int, int], Any]:
    months = {
        key: LiveCropMonth(live_days=0, days=days)
        for key, days in (
            ((2001, m), d) for m, d in ((7, 31), (8, 31), (9, 30), (10, 31), (11, 30))
        )
    }
    months.update(
        {
            (2001, 12): LiveCropMonth(live_days=0, days=31),
            (2002, 1): LiveCropMonth(live_days=0, days=31),
            (2002, 2): LiveCropMonth(live_days=0, days=28),
            (2002, 3): LiveCropMonth(live_days=0, days=31),
            (2002, 4): LiveCropMonth(live_days=0, days=30),
            (2002, 5): LiveCropMonth(live_days=0, days=31),
            (2002, 6): LiveCropMonth(live_days=0, days=30),
        }
    )
    months.update(changes.get("months", {}))
    return months


@pytest.mark.parametrize(
    ("live_days", "days", "expected"),
    [
        (16, 31, 1.0),  # just over half
        (15, 30, 0.0),  # exactly half: "most days" is more than half
        (14, 28, 0.0),  # exactly half of February
        (15, 31, 0.0),  # just under half
        (0, 31, 0.0),  # fallow (D222: the fallow under residue too)
        (31, 31, 1.0),  # every day
    ],
)
def test_the_state_is_one_above_half_of_the_days_and_zero_otherwise(
    live_days, days, expected
):
    assert producer.soil_cover_state(LiveCropMonth(live_days, days)) == expected


def test_the_series_carries_the_quantity_unit_provenance_and_source_of_d222():
    month = (2001, 7)
    forcing = producer_forcing(
        counts(months={month: LiveCropMonth(live_days=16, days=31)})
    )
    (series,) = forcing.soil_cover
    assert (series.quantity, series.unit) == ("soil_cover_state", "dimensionless")
    assert (series.start, series.end) == (forcing.horizon.start, forcing.horizon.end)
    assert series.provenance == "DERIVED"
    assert "D222" in series.source
    assert "exactly half" in series.source and "0.0" in series.source
    assert series.range_missing is not None
    by_month = cover_of(forcing)
    assert by_month[month].value == 1.0
    assert {item.value for key, item in by_month.items() if key != month} == {0.0}


def test_the_identifier_and_unit_are_those_run_rothc_reads():
    try:
        from engine.rothc import entry
    except ModuleNotFoundError:
        pytest.skip("engine.rothc is not built")
    assert entry.FORCING_QUANTITIES["soil_cover"] == (
        "soil_cover",
        producer.SOIL_COVER_STATE,
    )
    assert entry.DIMENSIONLESS == producer.SOIL_COVER_UNIT


def test_a_month_held_missing_keeps_its_reason_and_a_month_not_counted_has_none():
    held = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER day not known")
    months = counts(months={(2002, 2): held})
    del months[(2002, 3)]
    by_month = cover_of(producer_forcing(months))
    assert by_month[(2002, 2)].value is None
    assert by_month[(2002, 2)].missing.reason == "MISSING_INPUT"
    assert "PLACEHOLDER day not known" in by_month[(2002, 2)].missing.detail
    assert by_month[(2002, 3)].value is None
    assert by_month[(2002, 3)].missing.reason == "NO_COVERAGE"


def test_a_single_missing_or_no_count_writes_every_month_missing_never_zero():
    not_built = Missing(reason="NOT_AVAILABLE", detail="PLACEHOLDER not built")
    for given, reason, text in (
        (not_built, "NOT_AVAILABLE", "PLACEHOLDER not built"),
        (None, "NOT_AVAILABLE", "did not pass"),
    ):
        (series,) = producer_forcing(given).soil_cover
        assert all(item.value is None for item in series.months)
        assert {item.missing.reason for item in series.months} == {reason}
        assert text in series.months[0].missing.detail
        assert (series.provenance, series.source, series.range_missing) == (
            None,
            None,
            None,
        )


@pytest.mark.parametrize(
    "wrong",
    [
        LiveCropMonth(live_days=1, days=30),  # July has 31 days
        LiveCropMonth(live_days=32, days=31),  # more live days than days
        (16, 31),  # not a LiveCropMonth
    ],
)
def test_a_count_that_is_not_one_of_the_month_is_a_defect(wrong):
    with pytest.raises(TypeError):
        producer_forcing(counts(months={(2001, 7): wrong}))


# --- 2. the runner: the counts from the public rule ---------------------------------


def test_the_rule_is_discovered_by_its_public_name():
    assert runner.LIVE_CROP.module == "engine.water.living_crop"
    assert runner.LIVE_CROP.function == "live_crop_by_day"
    found = discover_engine_functions().live_crop_by_day
    try:
        from engine.water.living_crop import live_crop_by_day as public
    except ModuleNotFoundError:
        assert found is None
    else:
        assert found is public


def test_hand_made_calendar_through_the_runner():
    # Just over half, exactly half, fallow, a month crossing a harvest and a
    # missing stage length, with the real rule and the repository catalogue.
    parameters = repository_catalogue()
    longest = max(
        (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1
        for crop, start, end in CASES
        if crop == CROP
    )
    assert longest < stage_total(parameters, CROP)  # every day of them is live
    forcing, _ = run_rothc_on(hand_calendar(CASES), parameters=parameters)
    by_month = cover_of(forcing)
    assert list(by_month) == list(EXPECTED)
    for month, expected in EXPECTED.items():
        assert by_month[month].value == expected, month
    missing = by_month[(2002, 2)].missing
    assert missing.reason == "MISSING_INPUT"
    assert "2002-02-01" in missing.detail  # the first day not known is named
    assert "fao56_stage_length_" in missing.detail  # the stage length is named


def test_the_counts_are_the_days_with_a_live_crop_of_each_month():
    parameters = repository_catalogue()
    months = live_crop_months_for_forcing(
        live_crop_by_day(), hand_calendar(CASES), chain_climate(), parameters
    )
    assert isinstance(months, dict)
    for month, (live, days) in EXPECTED_LIVE_DAYS.items():
        assert months[month] == LiveCropMonth(live_days=live, days=days), month
    assert isinstance(months[(2002, 2)], Missing)


def test_no_climate_value_enters_the_cover():
    # The same dates with every value of every daily series changed, or held
    # missing: the cover is the same, month for month.
    base = chain_climate()
    changed = json.loads(base.model_dump_json())
    for series in changed["daily_series"]:
        for position, day in enumerate(series["days"]):
            if position % 2:
                series["days"][position] = {
                    "date": day["date"],
                    "value": None,
                    "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
                }
            else:
                day["value"] = 0.0
    calendar_ = hand_calendar(CASES)
    first, _ = run_rothc_on(calendar_, climate=base)
    second, _ = run_rothc_on(calendar_, climate=SiteClimate.model_validate(changed))
    assert first.soil_cover == second.soil_cover


def test_the_rule_gets_the_calendar_of_ep3_the_record_and_the_catalogue():
    calendar_ = hand_calendar(CASES)
    parameters = repository_catalogue()
    live = Fake({})
    forcing, water_fn = run_rothc_on(calendar_, live=live, parameters=parameters)
    ((args, kwargs),) = live.calls
    ((_, water_kwargs),) = water_fn.calls
    assert args[0] is water_kwargs["calendar"]  # the calendar EP3 reads
    assert args[1:] == producer.record_period(chain_climate())
    assert set(kwargs) == {"parameters"}
    assert kwargs["parameters"] is parameters  # the same object, unchanged
    # No day answered: every month NO_COVERAGE, never zero.
    assert {item.missing.reason for item in cover_of(forcing).values()} == {
        "NO_COVERAGE"
    }


def test_the_rule_is_called_once_per_phase_on_the_calendar_of_the_phase():
    from api.test_phases import THREE_YEARS, THREE_YEARS_PHASES, FakePhases

    calendar_fn, soil_fn, water_fn = fakes(calendar_answer=THREE_YEARS)
    phases = FakePhases(3, THREE_YEARS_PHASES)
    live = Fake({})
    engines = EntryPointEngines(
        EngineFunctions(
            build_rotation_calendar=calendar_fn,
            compute_soil_loss=soil_fn,
            compute_water_deficit_exposure=water_fn,
            run_rothc=Fake(balance(carbon_model="rothc")),
            live_crop_by_day=live,
            **phases.extra(),
        ),
        carbon_models=CARBON_MODELS,
    )
    result = engines.run(ROTATION, climate_result(chain_climate()), soil_result())
    assert len(live.calls) == len(result.phases) == 3
    for (args, _), (_, water_kwargs) in zip(live.calls, water_fn.calls, strict=True):
        assert args[0] is water_kwargs["calendar"]


def test_the_rule_not_built_gives_every_month_missing_naming_it():
    forcing, _ = run_rothc_on(hand_calendar(CASES), live=None)
    months = cover_of(forcing).values()
    assert all(item.value is None for item in months)
    assert {item.missing.reason for item in months} == {"NOT_AVAILABLE"}
    assert (
        "engine.water.living_crop.live_crop_by_day" in next(iter(months)).missing.detail
    )


def test_the_rule_is_not_called_when_no_forcing_can_be_laid_out():
    live = Fake({})
    short = json.loads(chain_climate().model_dump_json())
    for series in short["daily_series"]:
        series["days"] = series["days"][:40]
        series["end_date"] = series["days"][-1]["date"]
    months = live_crop_months_for_forcing(
        live, hand_calendar(CASES), SiteClimate.model_validate(short), {}
    )
    assert months is None
    assert live.calls == []


@pytest.mark.parametrize(
    "wrong",
    [
        [],
        {"2001-07-01": True},
        {dt.date(2001, 7, 1): 1},
        {dt.date(2001, 7, 1): "yes"},
    ],
)
def test_an_answer_of_another_shape_is_a_defect(wrong):
    with pytest.raises(TypeError):
        live_crop_months_for_forcing(
            Fake(wrong), hand_calendar(CASES), chain_climate(), {}
        )


def test_what_the_rule_raises_is_not_caught():
    with pytest.raises(RuntimeError):
        live_crop_months_for_forcing(
            Fake(raises=True), hand_calendar(CASES), chain_climate(), {}
        )


# --- 3. equality with EP3 on the rotations of D128 ---------------------------------


@pytest.mark.parametrize("rotation", ["soybean-winter-fallow", "wheat-soybean-maize"])
def test_each_count_is_the_days_on_which_ep3_asks_transpiration(monkeypatch, rotation):
    """On the two rotations of D128 (PLACEHOLDER years, month and day of
    USER-AP of D72), through the app with the real engines and the
    repository catalogue, in every phase: for each month EP3 computes on
    every day, the count of days with a live crop the runner passes to the
    producer equals the count of days on which EP3's daily balance asks
    transpiration (its demanded transpiration is a number; D106, D136, D157).
    """
    found = discover_engine_functions()
    if None in (
        found.build_rotation_calendar,
        found.compute_water_deficit_exposure,
        found.live_crop_by_day,
    ) or (found.run_amg is None and found.run_rothc is None):
        pytest.skip("the engines this comparison needs are not all built")
    try:
        from engine.water import exposure as ep3
    except ModuleNotFoundError:
        pytest.skip("EP3 is not built")
    if not hasattr(ep3, "_run_chain") or not hasattr(ep3, "NO_CROP_ON_THE_DAY"):
        pytest.skip("EP3's daily chain cannot be read in this layout")
    from api.test_runner_residues import _post_demo

    chains: list[list[Any]] = []
    real_chain = ep3._run_chain

    def recording_chain(*args: Any, **kwargs: Any) -> Any:
        days = real_chain(*args, **kwargs)
        chains.append(days)
        return days

    passed: list[Any] = []
    real_producer = runner.build_carbon_forcing

    def recording_producer(*args: Any, **kwargs: Any) -> Any:
        passed.append(kwargs["live_crop_months"])
        return real_producer(*args, **kwargs)

    monkeypatch.setattr(ep3, "_run_chain", recording_chain)
    monkeypatch.setattr(runner, "build_carbon_forcing", recording_producer)
    monkeypatch.setattr("api.app.discover_engine_functions", lambda: replace(found))
    _post_demo(rotation)
    assert len(chains) == len(passed) >= 1  # one of each per phase
    compared = live_months = bare_months = 0
    for chain, months in zip(chains, passed, strict=True):
        assert isinstance(months, dict)
        by_day = {day.date: day for day in chain}
        for (year, month), count in months.items():
            if not isinstance(count, LiveCropMonth):
                continue
            days = [
                dt.date(year, month, 1) + dt.timedelta(days=n)
                for n in range(count.days)
            ]
            demanded = [
                by_day[day].balance.transpiration_demanded
                for day in days
                if day in by_day
            ]
            if len(demanded) != count.days or any(
                isinstance(value, Missing) and value.reason != ep3.NO_CROP_ON_THE_DAY
                for value in demanded
            ):
                continue  # a month EP3 does not compute on every day
            asked = sum(1 for value in demanded if not isinstance(value, Missing))
            assert count.live_days == asked, (rotation, year, month)
            compared += 1
            live_months += count.live_days > 0
            bare_months += count.live_days < count.days
    if compared == 0:
        # Today: the repository catalogue holds the stage lengths of soybean
        # only, so the wheat and maize periods are not known (their months are
        # missing, never bare) and EP3 computes no whole month of this rotation.
        pytest.skip(
            f"EP3 computes no whole month of {rotation} with the repository "
            "catalogue, so there is no month to compare"
        )
    assert live_months > 0 and bare_months > 0
