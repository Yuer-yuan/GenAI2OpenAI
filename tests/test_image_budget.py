import copy
import json
import unittest
from unittest.mock import Mock

from flask import Flask

from anthropic_compat import apply_image_budget, create_anthropic_blueprint, input_token_count, to_openai_request


def image(number):
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,frame{number}"}}


def count_images(messages):
    return sum(part.get("type") == "image_url" for message in messages if isinstance(message.get("content"), list)
               for part in message["content"] if isinstance(part, dict))


def without_anchor_labels(message):
    return {**message, "content": [part for part in message["content"]
                                  if not (part.get("type") == "text" and part.get("text", "").startswith("[Retained image "))]}


def history(size=25, latest=2):
    messages = []
    for index in range(size):
        messages += [{"role": "user", "content": [image(index)]},
                     {"role": "assistant", "content": f"Observation {index}: saved facts"}]
    messages += [{"role": "user", "content": "Inspect the newly returned images; prior images are unrelated."},
                 {"role": "assistant", "tool_calls": [{"id": "new_read", "function": {"name": "Read", "arguments": "{}"}}]},
                 {"role": "tool", "tool_call_id": "new_read", "content": [
                     {"type": "text", "text": "before"}, *[image(size + i) for i in range(latest)],
                     {"type": "text", "text": "after"}]}]
    return messages


class ImageBudgetTests(unittest.TestCase):
    def test_under_limit_is_unchanged(self):
        messages = history(size=2, latest=2)
        self.assertIs(apply_image_budget(messages), messages)

    def test_prompt_wide_limit_preserves_pending_pixels_text_and_tool_ids(self):
        messages = history()
        original = copy.deepcopy(messages)
        bounded = apply_image_budget(messages)
        self.assertEqual(count_images(bounded), 20)
        self.assertEqual(messages, original)
        self.assertEqual(without_anchor_labels(bounded[-1]), messages[-1])
        self.assertEqual(bounded[-1]["tool_call_id"], "new_read")
        for index in range(25):
            self.assertEqual(bounded[index * 2 + 1], messages[index * 2 + 1])
        self.assertIn("Historical image", bounded[0]["content"][0]["text"])
        self.assertIn("re-read", bounded[0]["content"][0]["text"])
        self.assertEqual(apply_image_budget(bounded), bounded)

    def test_duplicates_keep_one_copy_with_explicit_references(self):
        messages = [{"role": "user", "content": [image(1) for _ in range(24)]}]
        bounded = apply_image_budget(messages)
        self.assertEqual(count_images(bounded), 1)
        text = json.dumps(bounded)
        self.assertEqual(text.count("Duplicate image:"), 23)
        self.assertIn("Retained image", text)

    def test_url_references_are_not_assumed_to_have_immutable_pixels(self):
        messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.com/live.png"}} for _ in range(21)]}]
        with self.assertRaisesRegex(ValueError, "batches of at most 20"):
            apply_image_budget(messages)

    def test_new_user_attachments_and_parallel_pending_results_are_protected(self):
        messages = history(size=25, latest=2)
        messages[-3]["content"] = [image(99), {"type": "text", "text": "Compare these with the tool images."}]
        bounded = apply_image_budget(messages, 3)
        self.assertEqual(count_images(bounded), 3)
        self.assertEqual(without_anchor_labels(bounded[-1]), messages[-1])
        self.assertEqual(without_anchor_labels(bounded[-3]), messages[-3])
        pending = {"role": "tool", "tool_call_id": "parallel", "content": [image(100)]}
        with self.assertRaisesRegex(ValueError, "no current images were discarded"):
            apply_image_budget([*messages, pending], 3)

    def test_repeating_latest_image_replaces_older_pixel_copy(self):
        messages = history(size=25, latest=1)
        messages[-1]["content"][1] = image(0)
        bounded = apply_image_budget(messages)
        self.assertEqual(without_anchor_labels(bounded[-1]), messages[-1])
        self.assertEqual(count_images(bounded), 20)
        self.assertIn("Duplicate image", bounded[0]["content"][0]["text"])

    def test_system_reminder_does_not_unpin_current_user_attachments(self):
        messages = history(size=25, latest=2)
        messages[-3]["content"] = [image(99)]
        messages.append({"role": "user", "content": "<system-reminder>Current tool context</system-reminder>"})
        with self.assertRaisesRegex(ValueError, "Current request needs 3"):
            apply_image_budget(messages, 2)

    def test_api_current_batch_over_limit_is_local_400_even_for_streaming(self):
        complete, stream = Mock(), Mock()
        app = Flask(__name__)
        app.register_blueprint(create_anthropic_blueprint(complete, stream))
        request = {"model": "deepseek", "max_tokens": 64, "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "url", "url": f"https://example.com/{i}.png"}} for i in range(21)]}]}
        for streaming in (False, True):
            result = app.test_client().post("/v1/messages", json={**request, "stream": streaming})
            self.assertEqual(result.status_code, 400)
            self.assertIn("batches", result.json["error"]["message"])
            self.assertEqual(result.json["error"]["type"], "invalid_request_error")
        complete.assert_not_called()
        stream.assert_not_called()

    def test_conversion_and_token_estimates_use_the_same_budget(self):
        messages = []
        for i in range(25):
            messages += [{"role": "user", "content": [{"type": "image", "source": {"type": "url", "url": f"https://example.com/{i}.png"}}]},
                         {"role": "assistant", "content": f"Observed {i}"}]
        messages.append({"role": "user", "content": "Summarize previous observations."})
        request = {"model": "deepseek", "max_tokens": 64, "messages": messages}
        normal = to_openai_request(request, max_images=7)
        counted = to_openai_request(request, count_only=True, max_images=7)
        self.assertEqual(count_images(normal["messages"]), 7)
        self.assertEqual(input_token_count(normal), input_token_count(counted))
        self.assertLess(input_token_count(normal), 1024 * 25)


if __name__ == "__main__":
    unittest.main()
