import json
from pathlib import Path
import unittest

from tools.benchmark_tools import AgentEnvironment, PROJECT, grade_calls


def call(name, args):
    return {"function": {"name": name, "arguments": json.dumps(args)}}


class BenchmarkGraderTests(unittest.TestCase):
    def test_unordered_calls_require_one_to_one_argument_matches(self):
        expected = [{"read": {"path": ["a"]}}, {"read": {"path": ["b"]}}]
        self.assertTrue(grade_calls([call("read", {"path": "b"}), call("read", {"path": "a"})], expected))
        self.assertFalse(grade_calls([call("read", {"path": "a"}), call("read", {"path": "a"})], expected))
        self.assertFalse(grade_calls([call("read", {"path": "a"})], expected))

    def test_schema_optional_omission_does_not_allow_wrong_or_extra_values(self):
        expected = [{"sort": {"values": [[3, 1]], "reverse": [False, ""]}}]
        self.assertTrue(grade_calls([call("sort", {"values": [3, 1]})], expected))
        self.assertFalse(grade_calls([call("sort", {"values": [1, 3]})], expected))
        self.assertFalse(grade_calls([call("sort", {"values": [3, 1], "reverse": 0})], expected))
        self.assertFalse(grade_calls([call("sort", {"values": [3, 1], "invented": 1})], expected))

    def test_agent_grader_rejects_self_report_and_incorrect_program(self):
        (PROJECT / "temp").mkdir(exist_ok=True)
        environment = AgentEnvironment("repair", 4827)
        try:
            self.assertFalse(environment.grade("CALC_OK; I ran it successfully"))
            environment.execute("Write", {"file_path": "calc.py", "content": "def add(a,b): return 0\nprint('CALC_OK')\n"})
            run = environment.execute("run_python", {"file_path": "calc.py"})
            self.assertFalse(environment.grade(run["run_id"]))
            environment.execute("Write", {"file_path": "calc.py", "content": "def add(a,b): return a+b\nprint('CALC_OK')\n"})
            run = environment.execute("run_python", {"file_path": "calc.py"})
            self.assertTrue(environment.grade(run["run_id"]))
        finally:
            environment.temp.cleanup()

    def test_state_and_execution_must_both_be_correct(self):
        environment = AgentEnvironment("pointer", 4827)
        try:
            value = min(environment.values)
            environment.execute("Write", {"file_path": "answer.json", "content": str(value + 1)})
            environment.execute("Write", {"file_path": "check.py", "content": f"print({value})"})
            run = environment.execute("run_python", {"file_path": "check.py"})
            self.assertFalse(environment.grade(run["run_id"]))
            with self.assertRaisesRegex(ValueError, "inside"):
                environment.execute("Read", {"file_path": "../outside.txt"})
        finally:
            environment.temp.cleanup()
