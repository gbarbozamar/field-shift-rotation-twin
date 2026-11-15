"""Residue engine (EP4 of contracts/ENTRYPOINTS.md). PROPOSED.

The one public function is ``build_residue_ledger``; see ``README.md`` in
this folder.
"""

from .ledger import build_residue_ledger

__all__ = ["build_residue_ledger"]
