"""The thin matrix through the decision (unit l2/thin-matrix-decision, #240).

``demo/`` runs the person-approved thin matrix — one field, three
rotations, all agricultural years, one uncertain input — through the
decision functions of ``decision/`` and emits the decision output
document of ``contracts/decision_output/``. The matrix lives in
``matrix.py``; ``run.py`` runs the decision over it; ``test_demo.py`` is
the acceptance test. Run, from the repository root::

    python -m pytest demo/
    python -m demo.run
"""
