import json
from pathlib import Path
import tempfile
import unittest

from tools.benchmark_vision import json_answer, make_request, score


class VisionBenchmarkTests(unittest.TestCase):
    def test_a_successful_refusal_is_not_image_understanding(self):
        expected = {"code": "A9QK43", "circles": 4}
        self.assertFalse(score({"unavailable": True}, expected)["passed"])
        self.assertFalse(score({"code": None, "circles": None}, expected)["passed"])
        self.assertTrue(score({"code": "A9QK43", "circles": 4}, expected)["passed"])

    def test_absent_keys_and_boolean_counts_do_not_pass(self):
        self.assertFalse(score({}, {"code": None})["passed"])
        self.assertFalse(score({"circles": True}, {"circles": 1})["passed"])
        self.assertTrue(score({"color": "Red"}, {"color": "red"})["passed"])
        self.assertEqual(json_answer('```json\n{"code":"A9QK43"}\n```'), {"code": "A9QK43"})

    def test_answer_is_not_in_prompt_and_control_omits_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "0.png"
            image.write_bytes(b"pixel fixture")
            case = {"paths": [image], "question": "Read the code.", "expected": {"code": "NEVER_IN_PROMPT_95821"}}
            request = make_request(case, "deepseek", "image")
            self.assertNotIn("NEVER_IN_PROMPT_95821", json.dumps(request))
            blocks = request["messages"][-1]["content"][0]["content"]
            self.assertEqual(blocks[0]["type"], "image")
            control = make_request(case, "deepseek", "no-image")
            self.assertNotIn('"type": "image"', json.dumps(control))
