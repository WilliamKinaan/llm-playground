"""Two CSV-backed data sets for this feature, each a single source of truth
parsed at import time - kept as CSV (not Python literals, unlike
`cases.py`/`catalog.py` in other features) since both are externally-sourced
tabular data, easy to diff or re-import if the user updates them.

- `test_cases.csv` -> TEST_CASES: known-answer {customer_message ->
  expected_department} pairs used by the "Run test suite" panel.
- `example_messages.csv` -> EXAMPLE_MESSAGES: sample messages for the
  "choose an example" dropdown on the "Try it" panel. No expected department
  attached - these exist to save typing, not to test the router.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from .schemas import Department, ExampleMessage

_FEATURE_DIR = Path(__file__).parent
_TEST_CASES_CSV_PATH = _FEATURE_DIR / "test_cases.csv"
_EXAMPLE_MESSAGES_CSV_PATH = _FEATURE_DIR / "example_messages.csv"


@dataclass(frozen=True)
class TestCase:
    test_id: str
    customer_message: str
    expected_department: Department
    category: str


def _load_test_cases() -> list[TestCase]:
    with _TEST_CASES_CSV_PATH.open(newline="", encoding="utf-8") as f:
        return [
            TestCase(
                test_id=row["test_id"],
                customer_message=row["customer_message"],
                expected_department=row["expected_department"],
                category=row["category"],
            )
            for row in csv.DictReader(f)
        ]


def _load_example_messages() -> list[ExampleMessage]:
    with _EXAMPLE_MESSAGES_CSV_PATH.open(newline="", encoding="utf-8") as f:
        return [
            ExampleMessage(message=row["message"], complexity=row["complexity"])
            for row in csv.DictReader(f)
        ]


TEST_CASES: list[TestCase] = _load_test_cases()
EXAMPLE_MESSAGES: list[ExampleMessage] = _load_example_messages()
