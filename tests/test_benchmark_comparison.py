import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.compare_tool_benchmarks import compare, load_reports
from tools.benchmark_tools import local_cases


def row(passed):
    return {"model": "test", "id": "example", "repeat": 0, "split": "holdout", "category": "execution",
            "passed": passed, "repairs": 0, "seconds": 1.0, "prompt_chars": 10}


class BenchmarkComparisonTests(unittest.TestCase):
    def test_completed_flag_does_not_hide_missing_attempts(self):
        cases = [case for case in local_cases() if case["split"] == "dev"]
        report = {"label": "test", "suite": "local", "split": "dev", "repeats": 1, "complete": True,
                  "dataset_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
                  "results": [{**row(True), "id": case["id"]} for case in cases[:-1]]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "coverage"):
                load_reports([path])

    def test_changed_dataset_fingerprint_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text(json.dumps({"complete": True, "suite": "local", "split": "dev", "dataset_sha256": "wrong"}))
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                load_reports([path])

    def test_unmatched_runs_cannot_be_reported_as_improvement(self):
        with self.assertRaisesRegex(ValueError, "same models"):
            compare({("test", "one", 0): row(False)}, {("test", "other", 0): row(True)})

    def test_failed_attempts_stay_in_denominator_and_changes_are_paired(self):
        key = ("test", "example", 0)
        report = compare({key: row(False)}, {key: row(True)})
        overall = next(item for item in report["tables"]["holdout"] if item["category"] == "all")
        self.assertEqual(overall["before"]["total"], 1)
        self.assertEqual(overall["before"]["success_rate"], 0)
        self.assertEqual(overall["after"]["success_rate"], 1)
        self.assertEqual(len(report["changed_outcomes"]), 1)


if __name__ == "__main__":
    unittest.main()
