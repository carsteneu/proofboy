"""The msheet engine: the runnable side of the Denk-Sprache V1.1.

A *sheet* is one answer of the model in the notation of
[05-02]/[05-07]: a free thinking zone (line heads strictly ``<tag><n>:``), an
append-only status register, and the strict claim zone
(``CLAIM``/``WITNESS``/``[HALT]``) whose claims witness-executing runner
writes the verdicts -- never the model.

Modules:

- :mod:`bemyself.msheet.library` -- the V1 library (exact integer functions
  with guards).
- :mod:`bemyself.msheet.formula` -- the V1 formula fragment (parser and
  evaluator).
- :mod:`bemyself.msheet.witnesses` -- the witness kinds and their execution.
- :mod:`bemyself.msheet.sheet` -- the sheet parser (thinking zone, statuses,
  claim zone).
- :mod:`bemyself.msheet.runner` -- execution of one sheet to its verdicts and
  the verdict appendix.

The command form is ``python3 -m bemyself.msheet run <file>``.
"""

from bemyself.msheet.formula import (
    Def,
    EmptyRangeError,
    EvaluationError,
    Formula,
    FormulaError,
    NotAFormula,
    UnboundedError,
    evaluate,
    evaluate_bool,
    parse_def,
    parse_formula,
)
from bemyself.msheet.library import GuardError

__all__ = [
    "Def",
    "EmptyRangeError",
    "EvaluationError",
    "Formula",
    "FormulaError",
    "GuardError",
    "NotAFormula",
    "UnboundedError",
    "evaluate",
    "evaluate_bool",
    "parse_def",
    "parse_formula",
]
