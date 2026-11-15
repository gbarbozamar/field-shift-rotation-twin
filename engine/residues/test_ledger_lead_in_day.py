"""The lead-in rule of the monthly carbon inputs on the second day of a month (unit U6 of #411).

``_month_value`` of ``engine/residues/ledger.py`` leaves missing, never zero,
every month before the first day the repeated calendar describes
(``RepeatedRotation.described_from``), and the month of that day when the
day is not the first of it (D221 of #77, the lead-in text ``LEAD_IN``).
``test_months_before_a_late_first_cycle_are_missing_never_zero`` in
``test_ledger.py`` reaches the rule through a calendar that starts late, on
the 20th and on the 1st; this file takes the 2nd, the first day for which
the month is not whole, so that the condition on the day (``day > 1``)
cannot move by one.

The first described day is set here, not drawn from a late calendar. Under
D188 part (2) of #77 (brief #372) the cycle before the first is laid out
whenever the first cycle starts late, so no late calendar gives a first
described day after the first day of the record's years; the rule of
``_month_value`` is still the one EP4 applies to whatever day the
repetition describes from. The calendar, the records and every number are
the PLACEHOLDER ones of ``test_ledger.py``; none is written here.

Run from the repository root:
``python -m pytest engine/residues/test_ledger_lead_in_day.py``.
"""

from __future__ import annotations

import datetime as dt

from engine.calendar.repeat import RepeatedRotation
from engine.residues.test_ledger import YEARS, run

FIRST_DAY = dt.date(2001, 9, 2)  # PLACEHOLDER: the first described day
UNKNOWN = [(2001, 7), (2001, 8), (2001, 9)]  # the months before it, and its own


def test_the_month_of_a_first_day_on_the_second_is_missing_never_zero(monkeypatch):
    monkeypatch.setattr(
        RepeatedRotation, "described_from", property(lambda self: FIRST_DAY)
    )
    ledger = run()
    assert ledger.first_ag_year == YEARS[0]
    assert ledger.monthly_carbon_inputs
    for found in ledger.monthly_carbon_inputs:
        for item in found.months:
            if (item.year, item.month) in UNKNOWN:
                assert item.value is None, (found.origin, item)
                assert item.missing.reason == "MISSING_INPUT"
                assert f"before {FIRST_DAY.isoformat()}" in item.missing.detail
                assert "before the first cycle" in item.missing.detail
            else:
                assert item.value is not None, (found.origin, item)
        missing = [(m.year, m.month) for m in found.months if m.value is None]
        assert missing == UNKNOWN, found.origin
