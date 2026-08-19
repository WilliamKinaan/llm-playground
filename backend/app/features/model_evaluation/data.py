"""Router step test cases: known-answer {customer_message -> expected_department}
pairs used by the "Run test suite" panel. Single source of truth, parsed from
`test_cases.csv` at import time - kept as CSV (not a Python literal, unlike
`cases.py`/`catalog.py` in other features) since it's externally-sourced
tabular data, easy to diff or re-import if the user updates it.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from .schemas import Department

_CSV_PATH = Path(__file__).parent / "test_cases.csv"


@dataclass(frozen=True)
class TestCase:
    test_id: str
    customer_message: str
    expected_department: Department
    category: str


def _load_test_cases() -> list[TestCase]:
    with _CSV_PATH.open(newline="", encoding="utf-8") as f:
        return [
            TestCase(
                test_id=row["test_id"],
                customer_message=row["customer_message"],
                expected_department=row["expected_department"],
                category=row["category"],
            )
            for row in csv.DictReader(f)
        ]


TEST_CASES: list[TestCase] = _load_test_cases()
