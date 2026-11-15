"""The thin matrix through the decision (unit l2/thin-matrix-decision, #240).

``demo/`` runs the person-approved thin matrix — one field, three
rotations, all agricultural years, one uncertain input — through the
decision functions of ``decision/`` and emits the decision output
document of ``contracts/decision_output/``. The matrix lives in
``matrix.py``; ``run.py`` runs the decision over it; ``test_demo.py`` is
the acceptance test. ``saved_case.py`` writes and checks the saved case
of the matrix (D177 of issue #77, issue #251), kept in
``saved_cases/example-case.json``; ``test_saved_case.py`` is its
acceptance test. Run, from the repository root::

    python -m pytest demo/
    python -m demo.run
    python -m demo.saved_case [YYYY-MM-DDTHH:MMZ]
"""
