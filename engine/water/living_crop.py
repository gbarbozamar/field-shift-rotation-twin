"""The days with a live crop in one crop period (decisions D135 and D136 of #77).

Unit ``l1/living-crop-days`` (issue #357). Three readers need the days on
which a live crop stands, under the rules of D135 and D136: the trivial
comparators of soil loss and water (D211, D212) and the monthly soil cover
of RothC (D222). Until this unit the rule lived only inside EP3
(``engine/water/exposure.py``, where the balance is given no crop on a
fallow day and on a day of the tail after maturity). This module holds it
once; EP3 reads it, and so can the other readers.

The rule, for one crop period from its sowing to its harvest (both
inclusive), with the four stage lengths of its crop:

- The four FAO-56 stages are laid end to end from the sowing, each with its
  length, never stretched to the period (D135); this is
  ``engine.water.stages.place_stages``.
- Stages that run past the harvest are cut there (D135): every day of the
  period up to the harvest is then a day with a live crop.
- Stages that end before the harvest leave a tail, from the day after the
  end of the late stage to the harvest: days with no live crop (D136).

The stage lengths are those of the crop, read from the parameter catalogue
by the exact scope ``{"crop": <crop>}`` (D137; ``live_crop_days_of_crop``),
as EP3 reads them. Only the stage lengths decide the days: a missing record
of the basal crop coefficient, or of the root depth, does not change which
days have a live crop (the crop is on the field), although EP3 does not
compute such a day. A stage length with no value leaves every day of the
period not known, missing with its reason, never a day with no crop (D79).
A length that is not a whole number of days of at least one leaves the
period ``NOT_COMPUTABLE``, as ``place_stages`` says why.

Pure functions (G1): no file, no network, no clock; the arguments are not
changed. No value of the method is here.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

from contracts.results.models import Missing
from engine.water._parameters import Catalogue, Scope
from engine.water.stages import (
    GROWTH_STAGES,
    STAGE_LENGTH_PARAMETERS,
    PlacedStages,
    place_stages,
)

__all__ = [
    "LiveCropDays",
    "live_crop_days",
    "live_crop_days_of_crop",
]

# The scope key of a parameter read by crop (EP3's ``CROP_KEY``).
_CROP_KEY = "crop"


@dataclass(frozen=True)
class LiveCropDays:
    """The days of one crop period, each with or without a live crop.

    ``stages`` holds the growth stage of every day with a live crop and, in
    ``stages.tail``, the days after the end of the late stage up to the
    harvest, with no live crop (D136).
    """

    sowing: dt.date
    harvest: dt.date
    stages: PlacedStages

    def is_live(self, day: dt.date) -> bool:
        """Whether a live crop stands on a day of the period.

        Raises ``ValueError`` for a day outside the period.
        """
        if day in self.stages:
            return True
        if day in self.stages.tail:
            return False
        raise ValueError(
            f"{day.isoformat()} lies outside the crop period from "
            f"{self.sowing.isoformat()} to {self.harvest.isoformat()}"
        )

    @property
    def days(self) -> dict[dt.date, bool]:
        """Every day of the period, from the sowing to the harvest, in order,
        with whether a live crop stands on it."""
        live = dict.fromkeys(self.stages, True)
        live.update(dict.fromkeys(self.stages.tail, False))
        return dict(sorted(live.items()))


def live_crop_days(
    sowing: dt.date,
    harvest: dt.date,
    lengths: Mapping[str, float | Missing],
    *,
    what: str,
) -> LiveCropDays | Missing:
    """The days with a live crop of one crop period (D135, D136).

    ``lengths`` holds the length in days of each stage of ``GROWTH_STAGES``,
    a number or the ``Missing`` the catalogue gave. ``what`` names the period
    and its crop in a ``detail``.

    Returns:

    - ``Missing`` with reason ``MISSING_INPUT`` when a stage length has no
      value: every day of the period is not known, never a day with no crop
      (D79); the detail names each missing length and repeats its reason;
    - ``Missing`` with reason ``NOT_COMPUTABLE`` when a length is not a whole
      number of days of at least one, as ``place_stages`` says;
    - otherwise the ``LiveCropDays`` of the period.

    Raises ``ValueError`` when ``harvest`` comes before ``sowing`` or a stage
    of ``GROWTH_STAGES`` is not in ``lengths`` (a defect of the caller).
    """
    absent = [stage for stage in GROWTH_STAGES if stage not in lengths]
    if absent:
        raise ValueError(f"{what}: no length given for the stage(s) {absent}")
    missing = {
        stage: value for stage, value in lengths.items() if isinstance(value, Missing)
    }
    if missing:
        return Missing(
            reason="MISSING_INPUT",
            detail=(
                f"the days with a live crop of {what} are not known: "
                + "; ".join(
                    f"the stage length '{STAGE_LENGTH_PARAMETERS[stage]}' has no "
                    f"value ({value.reason}: {value.detail})"
                    for stage, value in missing.items()
                )
                + "; missing stages stay missing (decision D79 of issue #77)"
            ),
        )
    placed = place_stages(sowing, harvest, dict(lengths), what=what)
    if isinstance(placed, Missing):
        return placed
    return LiveCropDays(sowing=sowing, harvest=harvest, stages=placed)


def live_crop_days_of_crop(
    sowing: dt.date,
    harvest: dt.date,
    crop: str,
    *,
    parameters: Mapping[str, dict],
    on: dt.date | None = None,
) -> LiveCropDays | Missing:
    """The days with a live crop of a period of ``crop``, from ``parameters``.

    The four stage lengths are read from the catalogue ``parameters`` (as
    ``params.catalogue.load_folder`` returns it) with the exact scope
    ``{"crop": crop}`` (D137), as EP3 reads them, on the day ``on`` (the
    sowing when it is not given); then ``live_crop_days``. No record but
    the four stage lengths is read: the basal crop coefficient and the root
    depth do not change the days.
    """
    catalogue = Catalogue(parameters)
    scope: Scope = ((_CROP_KEY, crop),)
    when = sowing if on is None else on
    lengths = {
        stage: catalogue.value(parameter_id, scope, when)
        for stage, parameter_id in STAGE_LENGTH_PARAMETERS.items()
    }
    return live_crop_days(sowing, harvest, lengths, what=f"a period of crop '{crop}'")
