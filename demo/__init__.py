"""The thin matrix through the decision (unit l2/thin-matrix-decision, #240).

``demo/`` runs the person-approved thin matrix — one field, three
rotations, all agricultural years, one uncertain input — through the
decision functions of ``decision/`` and emits the decision output
document of ``contracts/decision_output/``. The matrix lives in
``matrix.py``; ``run.py`` runs the decision over it; ``test_demo.py`` is
the acceptance test. ``saved_case.py`` writes and checks the saved case
of the matrix (D177 of issue #77, issue #251), kept in
``saved_cases/example-case.json``; ``test_saved_case.py`` is its
the acceptance test. ``real.py`` adds the tipping block of issue #267
(D3, D4, D10, D12) over the real route — the two rotations of the
demonstration of D128 at the two levels of the residue-cover block of
D75 (D115), phases nested by D117 — with ``test_real.py`` as its
acceptance test. Run, from the repository root::

    python -m pytest demo/
    python -m demo.run
    python -m demo.saved_case [YYYY-MM-DDTHH:MMZ]
    python -m demo.saved_case YYYY-MM-DD
    python -m demo.real
"""
