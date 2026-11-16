"""Tests for the 8-rubric farm input cost ledger.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

All prices, quantities, nutrient contents, and yields below are synthetic
invented test data from no real farm, supplier, or market.
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest
from pydantic import ValidationError

from economics.input_cost_ledger import (
    NUTRIENTS,
    RUBRICS,
    STATUS_MARKER,
    ActivityDeclaration,
    CostLineItem,
    CoverCropSavingSpec,
    InputCostLedgerReport,
    NutrientVector,
    PastureAmortizationSpec,
    PriceBookEntry,
    build_input_cost_ledger,
)


def _entry(
    item_id: str,
    unit_price: float | None,
    *,
    unit: str = "kg",
    currency: str = "USD",
    quote_date: str = "2026-10-01",
    source: str = "synthetic_coop_quote",
    tax_basis: str = "ex_tax",
    included_concepts: tuple[str, ...] = ("product",),
) -> PriceBookEntry:
    return PriceBookEntry(
        item_id=item_id,
        currency=currency,
        unit=unit,
        quote_date=quote_date,
        source=source,
        tax_basis=tax_basis,
        included_concepts=included_concepts,
        unit_price=unit_price,
    )


def test_rubrics_constant_and_status_marker() -> None:
    assert RUBRICS == (
        "seed",
        "fertilizer",
        "crop_protection",
        "field_operations",
        "harvest_freight",
        "pasture_establishment",
        "livestock",
        "structure_rent",
    )
    assert len(RUBRICS) == 8
    assert "PROPOSED" in STATUS_MARKER
    assert "Frontier Vision Rev13" in STATUS_MARKER


def test_complete_eight_rubric_ledger_and_json_roundtrip() -> None:
    price_book = [
        _entry(
            "PLACEHOLDER_seed", 4.0, unit="kg", included_concepts=("seed", "bagging")
        ),
        _entry("PLACEHOLDER_fert", 1.5, unit="kg"),
        _entry("PLACEHOLDER_herb", 12.0, unit="L"),
        _entry("PLACEHOLDER_ops", 35.0, unit="ha"),
        _entry(
            "PLACEHOLDER_freight",
            20.0,
            unit="t",
            included_concepts=("harvest", "freight"),
        ),
        _entry("PLACEHOLDER_pasture_seed", 180.0, unit="ha"),
        _entry("PLACEHOLDER_vet", 25.0, unit="head"),
        _entry("PLACEHOLDER_rent", 140.0, unit="ha"),
    ]
    activities = [
        ActivityDeclaration(
            ag_year=2026,
            crop_id="PLACEHOLDER_soybean",
            activity_kind="grain",
            required_rubrics=(
                "seed",
                "fertilizer",
                "crop_protection",
                "field_operations",
                "harvest_freight",
                "structure_rent",
            ),
            yield_t_ha=3.0,
            harvest_nutrient_removal_kg_ha=NutrientVector(
                N=150.0, P=15.0, K=45.0, S=9.0
            ),
        ),
        ActivityDeclaration(
            ag_year=2027,
            crop_id="PLACEHOLDER_pasture",
            activity_kind="pasture",
            required_rubrics=("pasture_establishment", "livestock", "structure_rent"),
            pasture_establishment_year=True,
            harvest_nutrient_removal_kg_ha=NutrientVector(N=0.0, P=0.0, K=0.0, S=0.0),
        ),
    ]
    items = [
        CostLineItem(
            rubric="seed",
            item_id="PLACEHOLDER_seed",
            ag_year=2026,
            crop_id="PLACEHOLDER_soybean",
            unit="kg",
            quantity=50.0,
        ),  # 200.0
        CostLineItem(
            rubric="fertilizer",
            item_id="PLACEHOLDER_fert",
            ag_year=2026,
            crop_id="PLACEHOLDER_soybean",
            unit="kg",
            quantity=100.0,
            nutrient_kg_per_unit=NutrientVector(N=0.10, P=0.20, K=0.0, S=0.10),
        ),  # 150.0; supplies N=10, P=20, K=0, S=10
        CostLineItem(
            rubric="crop_protection",
            item_id="PLACEHOLDER_herb",
            ag_year=2026,
            crop_id="PLACEHOLDER_soybean",
            unit="L",
            quantity=5.0,
        ),  # 60.0
        CostLineItem(
            rubric="field_operations",
            item_id="PLACEHOLDER_ops",
            ag_year=2026,
            crop_id="PLACEHOLDER_soybean",
            unit="ha",
            quantity=2.0,
        ),  # 70.0
        CostLineItem(
            rubric="harvest_freight",
            item_id="PLACEHOLDER_freight",
            ag_year=2026,
            crop_id="PLACEHOLDER_soybean",
            unit="t",
            quantity=1.0,
            scale_with_yield=True,
        ),  # 1.0 * 3.0 * 20.0 = 60.0
        CostLineItem(
            rubric="structure_rent",
            item_id="PLACEHOLDER_rent",
            ag_year=2026,
            unit="ha",
            quantity=1.0,
        ),  # 140.0
        CostLineItem(
            rubric="pasture_establishment",
            item_id="PLACEHOLDER_pasture_seed",
            ag_year=2027,
            crop_id="PLACEHOLDER_pasture",
            unit="ha",
            quantity=1.0,
        ),  # 180.0
        CostLineItem(
            rubric="livestock",
            item_id="PLACEHOLDER_vet",
            ag_year=2027,
            crop_id="PLACEHOLDER_pasture",
            unit="head",
            quantity=2.0,
        ),  # 50.0
        CostLineItem(
            rubric="structure_rent",
            item_id="PLACEHOLDER_rent",
            ag_year=2027,
            unit="ha",
            quantity=1.0,
        ),  # 140.0
    ]

    report = build_input_cost_ledger(activities, items, price_book, currency="USD")
    assert report.ledger_status == "complete"
    assert report.missing is None
    assert report.pending_rubrics == ()
    assert report.ag_years == (2026, 2027)
    assert set(report.rubrics) == set(RUBRICS)
    assert all(report.rubrics[r].status == "computed" for r in RUBRICS)

    # 2026 = 200 + 150 + 60 + 70 + 60 + 140 = 680.0
    # 2027 = 180 + 50 + 140 = 370.0
    assert report.by_year[2026].total_cost_per_ha == pytest.approx(680.0)
    assert report.by_year[2027].total_cost_per_ha == pytest.approx(370.0)
    assert report.total_cost_per_ha == pytest.approx(1050.0)
    assert report.annual_average_cost_per_ha == pytest.approx(525.0)
    assert report.pasture_allocation_mode == "concentrated_in_declared_year"
    assert report.price_book_audit["PLACEHOLDER_seed"].quote_date == dt.date(
        2026, 10, 1
    )
    assert report.price_book_audit["PLACEHOLDER_seed"].included_concepts == (
        "seed",
        "bagging",
    )

    dumped = report.model_dump(mode="json")
    reloaded = InputCostLedgerReport.model_validate(dumped)
    assert reloaded == report
    assert InputCostLedgerReport.model_validate_json(report.model_dump_json()) == report


def test_price_book_entry_strict_validation() -> None:
    # Accepts list for included_concepts and date object
    entry = PriceBookEntry(
        item_id="PLACEHOLDER_item",
        currency="USD",
        unit="kg",
        quote_date=dt.date(2026, 11, 1),
        source="user",
        tax_basis="inc_tax",
        included_concepts=["product", "delivery"],
        unit_price=10.0,
    )
    assert entry.included_concepts == ("product", "delivery")

    with pytest.raises(ValidationError):
        PriceBookEntry(
            item_id="PLACEHOLDER_item",
            currency="USD",
            unit="kg",
            quote_date="2026-11-01",
            source="user",
            tax_basis="ex_tax",
            included_concepts=("product",),
            unit_price=-1.0,
        )

    with pytest.raises(ValidationError):
        PriceBookEntry(
            item_id="PLACEHOLDER_item",
            currency="USD",
            unit="kg",
            quote_date="2026-11-01",
            source="user",
            tax_basis="ex_tax",
            included_concepts=("product",),
            unit_price=float("nan"),
        )

    with pytest.raises(ValidationError):
        PriceBookEntry(
            item_id="PLACEHOLDER_item",
            currency="USD",
            unit="kg",
            quote_date="2026-11-01",
            source="user",
            tax_basis="ex_tax",
            included_concepts=("product",),
            unit_price=True,  # type: ignore[arg-type]
        )

    with pytest.raises(ValidationError):
        PriceBookEntry(
            item_id="PLACEHOLDER_item",
            currency="USD",
            unit="kg",
            quote_date="2026-11-01",
            source="user",
            tax_basis="ex_tax",
            included_concepts=("product",),
            unit_price=5.0,
            missing={"reason": "NOT_DECLARED"},  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="duplicate item_id"):
        build_input_cost_ledger(
            [ActivityDeclaration(ag_year=2026, crop_id="PLACEHOLDER_c")],
            [],
            [_entry("dup", 1.0), _entry("dup", 2.0)],
            currency="USD",
        )


def test_rule1_currency_and_unit_mismatches() -> None:
    activities = [
        ActivityDeclaration(
            ag_year=2026, crop_id="PLACEHOLDER_corn", required_rubrics=("seed",)
        ),
        ActivityDeclaration(
            ag_year=2027, crop_id="PLACEHOLDER_soy", required_rubrics=("seed",)
        ),
    ]

    # Currency mismatch between price book and ledger currency
    with pytest.raises(ValueError, match="currency mismatch"):
        build_input_cost_ledger(
            activities[:1],
            [
                CostLineItem(
                    rubric="seed",
                    item_id="seed_uyu",
                    ag_year=2026,
                    unit="kg",
                    quantity=20.0,
                )
            ],
            [_entry("seed_uyu", 100.0, currency="UYU", unit="kg")],
            currency="USD",
        )

    # Same mismatch with on_mismatch="not_computable" emits typed NOT_COMPUTABLE
    report_curr = build_input_cost_ledger(
        activities[:1],
        [
            CostLineItem(
                rubric="seed",
                item_id="seed_uyu",
                ag_year=2026,
                unit="kg",
                quantity=20.0,
            )
        ],
        [_entry("seed_uyu", 100.0, currency="UYU", unit="kg")],
        currency="USD",
        on_mismatch="not_computable",
    )
    assert report_curr.ledger_status == "not_computable"
    assert report_curr.total_cost_per_ha is None
    assert report_curr.missing is not None
    assert report_curr.missing.reason == "NOT_COMPUTABLE"
    assert report_curr.rubrics["seed"].status == "not_computable"
    assert report_curr.rubrics["seed"].missing is not None
    assert report_curr.rubrics["seed"].missing.reason == "NOT_COMPUTABLE"

    # Unit mismatch between line item and price book
    with pytest.raises(ValueError, match="unit mismatch"):
        build_input_cost_ledger(
            activities[:1],
            [
                CostLineItem(
                    rubric="seed",
                    item_id="seed_bag",
                    ag_year=2026,
                    unit="kg",
                    quantity=20.0,
                )
            ],
            [_entry("seed_bag", 80.0, currency="USD", unit="bag")],
            currency="USD",
        )

    report_unit = build_input_cost_ledger(
        activities[:1],
        [
            CostLineItem(
                rubric="seed",
                item_id="seed_bag",
                ag_year=2026,
                unit="kg",
                quantity=20.0,
            )
        ],
        [_entry("seed_bag", 80.0, currency="USD", unit="bag")],
        currency="USD",
        on_mismatch="not_computable",
    )
    assert report_unit.ledger_status == "not_computable"
    assert report_unit.rubrics["seed"].status == "not_computable"

    # Cross-year unit mismatch on same item_id
    with pytest.raises(ValueError, match="unit mismatch across line items"):
        build_input_cost_ledger(
            activities,
            [
                CostLineItem(
                    rubric="seed",
                    item_id="seed_x",
                    ag_year=2026,
                    unit="kg",
                    quantity=20.0,
                ),
                CostLineItem(
                    rubric="seed",
                    item_id="seed_x",
                    ag_year=2027,
                    unit="t",
                    quantity=0.02,
                ),
            ],
            [_entry("seed_x", 5.0, unit="kg")],
            currency="USD",
        )


def test_rule2_missing_price_or_quantity_never_zero() -> None:
    activities = [
        ActivityDeclaration(
            ag_year=2026,
            crop_id="PLACEHOLDER_wheat",
            required_rubrics=("seed", "fertilizer", "crop_protection"),
        )
    ]
    price_book = [
        _entry("seed_wheat", 2.0, unit="kg"),
        _entry("fert_unloaded", None, unit="kg"),  # unloaded price
    ]
    items = [
        CostLineItem(
            rubric="seed",
            item_id="seed_wheat",
            ag_year=2026,
            crop_id="PLACEHOLDER_wheat",
            unit="kg",
            quantity=100.0,
        ),  # computed: 200.0
        CostLineItem(
            rubric="fertilizer",
            item_id="fert_unloaded",
            ag_year=2026,
            crop_id="PLACEHOLDER_wheat",
            unit="kg",
            quantity=80.0,
        ),  # pending: unloaded price
        # crop_protection required but has NO line item -> pending
    ]

    report = build_input_cost_ledger(activities, items, price_book, currency="USD")
    assert report.ledger_status == "incomplete"
    assert report.total_cost_per_ha is None
    assert report.annual_average_cost_per_ha is None
    assert report.missing is not None
    assert report.missing.reason == "MISSING_INPUT"

    assert report.rubrics["seed"].status == "computed"
    assert report.rubrics["seed"].total_cost_per_ha == pytest.approx(200.0)

    for pending_rubric in ("fertilizer", "crop_protection"):
        entry = report.rubrics[pending_rubric]
        assert entry.status == "pending"
        assert entry.total_cost_per_ha is None  # NEVER 0.0
        assert entry.annual_average_cost_per_ha is None
        assert entry.missing is not None
        assert entry.missing.reason == "MISSING_INPUT"

    assert set(report.pending_rubrics) == {"fertilizer", "crop_protection"}
    assert report.rubrics["livestock"].status == "not_applicable"
    assert report.rubrics["livestock"].total_cost_per_ha is None
    assert report.by_year[2026].status == "incomplete"
    assert report.by_year[2026].total_cost_per_ha is None

    # Missing quantity case
    report_missing_qty = build_input_cost_ledger(
        [
            ActivityDeclaration(
                ag_year=2026, crop_id="PLACEHOLDER_w", required_rubrics=("seed",)
            )
        ],
        [
            CostLineItem(
                rubric="seed",
                item_id="seed_wheat",
                ag_year=2026,
                unit="kg",
                quantity=None,
            )
        ],
        [_entry("seed_wheat", 2.0, unit="kg")],
        currency="USD",
    )
    assert report_missing_qty.ledger_status == "incomplete"
    assert report_missing_qty.rubrics["seed"].status == "pending"
    assert report_missing_qty.rubrics["seed"].total_cost_per_ha is None

    # Unlisted item_id in price_book case
    report_missing_item = build_input_cost_ledger(
        [
            ActivityDeclaration(
                ag_year=2026, crop_id="PLACEHOLDER_w", required_rubrics=("seed",)
            )
        ],
        [
            CostLineItem(
                rubric="seed",
                item_id="not_in_book",
                ag_year=2026,
                unit="kg",
                quantity=50.0,
            )
        ],
        [],
        currency="USD",
    )
    assert report_missing_item.ledger_status == "incomplete"
    assert report_missing_item.rubrics["seed"].status == "pending"
    assert report_missing_item.rubrics["seed"].missing is not None
    assert report_missing_item.rubrics["seed"].missing.reason == "MISSING_INPUT"


def test_rule2_double_crop_requires_each_crop_covered() -> None:
    activities = [
        ActivityDeclaration(
            ag_year=2026, crop_id="PLACEHOLDER_wheat", required_rubrics=("seed",)
        ),
        ActivityDeclaration(
            ag_year=2026, crop_id="PLACEHOLDER_soy_2nd", required_rubrics=("seed",)
        ),
    ]
    report = build_input_cost_ledger(
        activities,
        [
            CostLineItem(
                rubric="seed",
                item_id="seed_w",
                ag_year=2026,
                crop_id="PLACEHOLDER_wheat",
                unit="kg",
                quantity=100.0,
            )
        ],
        [_entry("seed_w", 1.5, unit="kg")],
        currency="USD",
    )
    assert report.ledger_status == "incomplete"
    assert report.rubrics["seed"].status == "pending"
    assert "PLACEHOLDER_soy_2nd" in (report.rubrics["seed"].missing.detail or "")


def test_rule3_fertilizer_nutrient_balance_mining_surplus_and_no_fabrication() -> None:
    price_book = [
        _entry("urea", 0.8, unit="kg"),
        _entry("map", 1.2, unit="kg"),
        _entry("kcl", 0.7, unit="kg"),
    ]
    activities = [
        ActivityDeclaration(
            ag_year=2026,
            crop_id="PLACEHOLDER_maize",
            required_rubrics=("fertilizer",),
            yield_t_ha=5.0,
            # N=20*5=100, P=4*5=20, K=6*5=30, S=2*5=10
            nutrient_removal_kg_per_t=NutrientVector(N=20.0, P=4.0, K=6.0, S=2.0),
        )
    ]
    items = [
        CostLineItem(
            rubric="fertilizer",
            item_id="urea",
            ag_year=2026,
            crop_id="PLACEHOLDER_maize",
            unit="kg",
            quantity=100.0,
            nutrient_kg_per_unit=NutrientVector(N=0.46),  # 46 kg N -> net mining (-54)
        ),
        CostLineItem(
            rubric="fertilizer",
            item_id="map",
            ag_year=2026,
            crop_id="PLACEHOLDER_maize",
            unit="kg",
            quantity=100.0,
            # N=11 -> total N=57 (-43 mining); P=22 -> surplus (+2); S=10 -> balanced (0)
            nutrient_kg_per_unit=NutrientVector(N=0.11, P=0.22, S=0.10),
        ),
        CostLineItem(
            rubric="fertilizer",
            item_id="kcl",
            ag_year=2026,
            crop_id="PLACEHOLDER_maize",
            unit="kg",
            quantity=100.0,
            # K=50 -> surplus (+20)
        ),
    ]
    report = build_input_cost_ledger(
        activities,
        items,
        price_book,
        currency="USD",
        fertilizer_compositions={"kcl": NutrientVector(K=0.50)},
    )
    assert report.ledger_status == "complete"
    nb = report.nutrient_balance_kg_ha
    assert set(nb) == set(NUTRIENTS)

    assert nb["N"].supplied_kg_ha == pytest.approx(57.0)
    assert nb["N"].removed_kg_ha == pytest.approx(100.0)
    assert nb["N"].balance_kg_ha == pytest.approx(-43.0)
    assert nb["N"].status == "net_mining"

    assert nb["P"].supplied_kg_ha == pytest.approx(22.0)
    assert nb["P"].removed_kg_ha == pytest.approx(20.0)
    assert nb["P"].balance_kg_ha == pytest.approx(2.0)
    assert nb["P"].status == "surplus"

    assert nb["K"].supplied_kg_ha == pytest.approx(50.0)
    assert nb["K"].removed_kg_ha == pytest.approx(30.0)
    assert nb["K"].balance_kg_ha == pytest.approx(20.0)
    assert nb["K"].status == "surplus"

    assert nb["S"].supplied_kg_ha == pytest.approx(10.0)
    assert nb["S"].removed_kg_ha == pytest.approx(10.0)
    assert nb["S"].balance_kg_ha == pytest.approx(0.0)
    assert nb["S"].status == "balanced"

    assert report.net_mining_nutrients == ("N",)
    assert report.surplus_nutrients == ("P", "K")

    # Without declared crop harvest nutrient removal -> pending, never fabricated!
    report_no_removal = build_input_cost_ledger(
        [
            ActivityDeclaration(
                ag_year=2026,
                crop_id="PLACEHOLDER_maize",
                required_rubrics=("fertilizer",),
                yield_t_ha=5.0,
            )
        ],
        [items[0]],
        price_book,
        currency="USD",
    )
    assert report_no_removal.ledger_status == "complete"
    for n in NUTRIENTS:
        elem = report_no_removal.nutrient_balance_kg_ha[n]
        assert elem.status == "pending"
        assert elem.balance_kg_ha is None
        assert elem.missing is not None
        assert elem.missing.reason == "MISSING_INPUT"

    # Without fertilizer composition -> pending, never fabricated!
    report_no_comp = build_input_cost_ledger(
        activities,
        [
            CostLineItem(
                rubric="fertilizer",
                item_id="urea",
                ag_year=2026,
                crop_id="PLACEHOLDER_maize",
                unit="kg",
                quantity=100.0,
            )
        ],
        price_book,
        currency="USD",
    )
    for n in NUTRIENTS:
        assert report_no_comp.nutrient_balance_kg_ha[n].status == "pending"
        assert report_no_comp.nutrient_balance_kg_ha[n].supplied_kg_ha is None


def test_rule4_crop_protection_refuses_assumed_cover_crop_savings() -> None:
    activity = ActivityDeclaration(
        ag_year=2026, crop_id="PLACEHOLDER_cover", activity_kind="cover"
    )
    item = CostLineItem(
        rubric="crop_protection", item_id="herb_a", ag_year=2026, unit="L", quantity=3.0
    )
    book = [_entry("herb_a", 15.0, unit="L")]

    # Policy flag cannot be disabled
    with pytest.raises(ValueError, match="cover_crop_savings_must_be_explicit"):
        build_input_cost_ledger(
            [activity],
            [item],
            book,
            currency="USD",
            cover_crop_savings_must_be_explicit=False,
        )

    # Activity assuming savings is refused
    with pytest.raises(ValueError, match="cover_crop_savings_must_be_explicit"):
        ActivityDeclaration(
            ag_year=2026,
            crop_id="PLACEHOLDER_cover",
            activity_kind="cover",
            assume_cover_crop_herbicide_savings=True,
        )

    # Line item assuming savings is refused
    with pytest.raises(ValueError, match="cover_crop_savings_must_be_explicit"):
        CostLineItem(
            rubric="crop_protection",
            item_id="herb_a",
            ag_year=2026,
            unit="L",
            quantity=3.0,
            assume_cover_crop_herbicide_savings=True,
        )

    # Non-explicit or assumed CoverCropSavingSpec is refused
    with pytest.raises(ValueError, match="explicit"):
        CoverCropSavingSpec(
            is_explicit=False, saving_amount_per_ha=10.0, justification="trial"
        )
    with pytest.raises(ValueError, match="assumed"):
        CoverCropSavingSpec(
            is_explicit=True,
            assumed=True,
            saving_amount_per_ha=10.0,
            justification="trial",
        )

    # Explicit entered saving works and deducts transparently
    explicit_item = CostLineItem(
        rubric="crop_protection",
        item_id="herb_a",
        ag_year=2026,
        unit="L",
        quantity=4.0,  # 4 * 15 = 60.0 gross
        cover_crop_saving=CoverCropSavingSpec(
            is_explicit=True,
            saving_amount_per_ha=20.0,
            justification="user_entered_reduced_post_emergent_pass",
        ),
    )
    report = build_input_cost_ledger([activity], [explicit_item], book, currency="USD")
    assert report.rubrics["crop_protection"].total_cost_per_ha == pytest.approx(40.0)
    assert report.cover_crop_savings_must_be_explicit is True

    # Explicit saving exceeding gross cost is refused
    too_large_saving = CostLineItem(
        rubric="crop_protection",
        item_id="herb_a",
        ag_year=2026,
        unit="L",
        quantity=1.0,  # 15.0 gross
        cover_crop_saving=CoverCropSavingSpec(
            is_explicit=True,
            saving_amount_per_ha=25.0,
            justification="over_deduction",
        ),
    )
    with pytest.raises(ValueError, match="exceeds gross"):
        build_input_cost_ledger([activity], [too_large_saving], book, currency="USD")


def test_rule5_pasture_establishment_concentrates_unless_explicitly_amortized() -> None:
    activities = [
        ActivityDeclaration(
            ag_year=y,
            crop_id="PLACEHOLDER_pasture",
            activity_kind="pasture",
            pasture_establishment_year=(y == 2026),
        )
        for y in (2026, 2027, 2028)
    ]
    book = [_entry("pasture_est", 300.0, unit="ha")]

    # Default: concentrated 100% in declared establishment year (2026)
    concentrated = build_input_cost_ledger(
        activities,
        [
            CostLineItem(
                rubric="pasture_establishment",
                item_id="pasture_est",
                ag_year=2026,
                unit="ha",
                quantity=1.0,
            )
        ],
        book,
        currency="USD",
    )
    pe = concentrated.rubrics["pasture_establishment"]
    assert concentrated.pasture_allocation_mode == "concentrated_in_declared_year"
    assert pe.allocation_mode == "concentrated_in_declared_year"
    assert pe.cost_by_year[2026] == pytest.approx(300.0)
    assert pe.cost_by_year[2027] is None
    assert pe.cost_by_year[2028] is None
    assert pe.total_cost_per_ha == pytest.approx(300.0)
    assert pe.annual_average_cost_per_ha == pytest.approx(100.0)

    # Explicit amortization across declared years
    amortized = build_input_cost_ledger(
        activities,
        [
            CostLineItem(
                rubric="pasture_establishment",
                item_id="pasture_est",
                ag_year=2026,
                unit="ha",
                quantity=1.0,
                pasture_amortization=PastureAmortizationSpec(
                    amortize=True, target_ag_years=(2026, 2027, 2028)
                ),
            )
        ],
        book,
        currency="USD",
    )
    pe_a = amortized.rubrics["pasture_establishment"]
    assert amortized.pasture_allocation_mode == "explicitly_amortized"
    assert pe_a.cost_by_year == {
        2026: pytest.approx(100.0),
        2027: pytest.approx(100.0),
        2028: pytest.approx(100.0),
    }
    assert pe_a.total_cost_per_ha == pytest.approx(300.0)

    # Validation guards on PastureAmortizationSpec
    with pytest.raises(ValueError, match="non-empty target_ag_years"):
        PastureAmortizationSpec(amortize=True, target_ag_years=())
    with pytest.raises(ValueError, match="weights must sum to 1.0"):
        PastureAmortizationSpec(
            amortize=True, target_ag_years=(2026, 2027), weights=(0.5, 0.3)
        )
    with pytest.raises(ValueError, match="not in declared activities"):
        build_input_cost_ledger(
            activities,
            [
                CostLineItem(
                    rubric="pasture_establishment",
                    item_id="pasture_est",
                    ag_year=2026,
                    unit="ha",
                    quantity=1.0,
                    pasture_amortization=PastureAmortizationSpec(
                        amortize=True, target_ag_years=(2026, 2099)
                    ),
                )
            ],
            book,
            currency="USD",
        )


def test_rule5_harvest_freight_scales_linearly_with_yield() -> None:
    activities = [
        ActivityDeclaration(
            ag_year=2026,
            crop_id="PLACEHOLDER_soy",
            required_rubrics=("harvest_freight",),
            yield_t_ha=2.5,
        ),
        ActivityDeclaration(
            ag_year=2027,
            crop_id="PLACEHOLDER_soy",
            required_rubrics=("harvest_freight",),
            yield_t_ha=5.0,
        ),
    ]
    items = [
        CostLineItem(
            rubric="harvest_freight",
            item_id="freight_t",
            ag_year=2026,
            crop_id="PLACEHOLDER_soy",
            unit="t",
            quantity=1.0,
            scale_with_yield=True,
        ),
        CostLineItem(
            rubric="harvest_freight",
            item_id="freight_t",
            ag_year=2027,
            crop_id="PLACEHOLDER_soy",
            unit="t",
            quantity=1.0,
            scale_with_yield=True,
        ),
    ]
    book = [_entry("freight_t", 30.0, unit="t")]

    report = build_input_cost_ledger(activities, items, book, currency="USD")
    hf = report.rubrics["harvest_freight"]
    assert hf.status == "computed"
    assert hf.cost_by_year[2026] == pytest.approx(75.0)
    assert hf.cost_by_year[2027] == pytest.approx(150.0)
    assert hf.cost_by_year[2027] == pytest.approx(2.0 * hf.cost_by_year[2026])

    # Missing yield keeps harvest_freight pending (NEVER 0.0)
    missing_yield_report = build_input_cost_ledger(
        [
            ActivityDeclaration(
                ag_year=2026,
                crop_id="PLACEHOLDER_soy",
                required_rubrics=("harvest_freight",),
                yield_t_ha=None,
                yield_missing={"reason": "NOT_DECLARED"},  # type: ignore[arg-type]
            )
        ],
        [items[0]],
        book,
        currency="USD",
    )
    assert missing_yield_report.ledger_status == "incomplete"
    assert missing_yield_report.rubrics["harvest_freight"].status == "pending"
    assert missing_yield_report.rubrics["harvest_freight"].total_cost_per_ha is None

    # scale_with_yield rejected on non-harvest_freight rubrics
    with pytest.raises(ValueError, match="harvest_freight"):
        CostLineItem(
            rubric="seed",
            item_id="freight_t",
            ag_year=2026,
            unit="t",
            quantity=1.0,
            scale_with_yield=True,
        )


def test_immutability_and_no_input_mutation() -> None:
    activities = [
        ActivityDeclaration(
            ag_year=2026, crop_id="PLACEHOLDER_c", required_rubrics=("seed",)
        )
    ]
    items = [
        CostLineItem(
            rubric="seed", item_id="seed_c", ag_year=2026, unit="kg", quantity=10.0
        )
    ]
    book = {"seed_c": _entry("seed_c", 5.0, unit="kg")}
    activities_snap = copy.deepcopy(activities)
    items_snap = copy.deepcopy(items)
    book_snap = copy.deepcopy(book)

    report = build_input_cost_ledger(activities, items, book, currency="USD")
    assert activities == activities_snap
    assert items == items_snap
    assert book == book_snap

    with pytest.raises(ValidationError):
        report.ledger_status = "incomplete"  # type: ignore[misc]
