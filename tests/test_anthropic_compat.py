import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import struct
import unittest
import zlib
from unittest.mock import Mock, patch

from flask import Flask

from anthropic_compat import create_anthropic_blueprint, input_token_count, to_openai_request


PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"


def image_block(data=PNG):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def image_tool_request(model="deepseek"):
    return {"model": model, "max_tokens": 128, "messages": [
        {"role": "user", "content": "Read the image and report its accompanying text honestly."},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "image_read", "name": "Read", "input": {"file_path": "fixture.png"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "image_read", "content": [
            {"type": "text", "text": "before image"}, image_block(), {"type": "text", "text": "after image"}]}]}]}


def events(response):
    return [json.loads(line[6:]) for line in response.data.decode().splitlines() if line.startswith("data: ")]


class AnthropicCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.completion = {"model": "glm", "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}]}
        self.complete = Mock(side_effect=lambda payload: self.completion)
        self.stream = Mock(return_value=iter([{"type": "delta", "content": "hello"}, {"type": "done"}]))
        app = Flask(__name__)
        app.register_blueprint(create_anthropic_blueprint(self.complete, self.stream))
        self.client = app.test_client()
        self.payload = {"model": "glm", "max_tokens": 64, "messages": [{"role": "user", "content": "Hi"}]}

    def test_tool_use_and_results_keep_ids_and_text(self):
        data = {**self.payload, "system": [{"type": "text", "text": "system"}], "messages": [
            {"role": "user", "content": "read"},
            {"role": "assistant", "content": [{"type": "text", "text": "checking"},
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "a.txt"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": "answer"}]}]},
        ]}
        converted = to_openai_request(data)
        self.assertEqual(converted["messages"][0], {"role": "system", "content": "system"})
        assistant = converted["messages"][2]
        self.assertEqual(assistant["content"], "checking")
        self.assertEqual(assistant["tool_calls"][0]["id"], "toolu_1")
        self.assertEqual(json.loads(assistant["tool_calls"][0]["function"]["arguments"]), {"file_path": "a.txt"})
        self.assertEqual(converted["messages"][3], {"role": "tool", "tool_call_id": "toolu_1", "content": "answer"})

    def test_tool_choice_and_schema(self):
        tool = {"name": "Read", "input_schema": {"type": "object", "properties": {}}}
        data = {**self.payload, "tools": [tool], "tool_choice": {"type": "tool", "name": "Read"}}
        converted = to_openai_request(data)
        self.assertEqual(converted["tool_choice"]["function"]["name"], "Read")
        self.assertEqual(converted["tools"][0]["function"]["parameters"], tool["input_schema"])
        data["tool_choice"] = {"type": "any"}
        self.assertEqual(to_openai_request(data)["tool_choice"], "required")

    def test_claude_code_inline_system_message(self):
        data = {**self.payload, "messages": [{"role": "system", "content": [{"type": "text", "text": "Be concise"}]}, *self.payload["messages"]]}
        self.assertEqual(to_openai_request(data)["messages"][0], {"role": "system", "content": "Be concise"})

    def test_non_streaming_response(self):
        response = self.client.post("/v1/messages", json=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["content"], [{"type": "text", "text": "hello"}])
        self.assertEqual(response.json["stop_reason"], "end_turn")

    def test_text_stream_and_length_stop(self):
        self.stream.return_value = iter([{"type": "delta", "content": "hello"}, {"type": "done", "finish_reason": "length"}])
        response = self.client.post("/v1/messages", json={**self.payload, "stream": True})
        result = events(response)
        self.assertEqual([e["type"] for e in result], ["message_start", "content_block_start", "content_block_delta", "content_block_stop", "message_delta", "message_stop"])
        self.assertEqual(result[2]["delta"]["text"], "hello")
        self.assertEqual(result[-2]["delta"]["stop_reason"], "max_tokens")
        self.complete.assert_not_called()

    def test_tool_stream_emits_reconstructible_input(self):
        self.completion = {"model": "glm", "choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
            {"id": "toolu_a", "function": {"name": "Read", "arguments": '{"file_path":"hello.txt"}'}}
        ]}}]}
        payload = {**self.payload, "stream": True, "tools": [{"name": "Read", "input_schema": {"type": "object"}}]}
        result = events(self.client.post("/v1/messages", json=payload))
        self.assertEqual(result[1]["content_block"], {"type": "tool_use", "id": "toolu_a", "name": "Read", "input": {}})
        self.assertEqual(json.loads(result[2]["delta"]["partial_json"]), {"file_path": "hello.txt"})
        self.assertEqual(result[-2]["delta"]["stop_reason"], "tool_use")

    def test_count_tokens_does_not_require_max_tokens(self):
        payload = {k: v for k, v in self.payload.items() if k != "max_tokens"}
        response = self.client.post("/v1/messages/count_tokens", json=payload)
        self.assertGreater(response.json["input_tokens"], 0)
        self.complete.assert_not_called()

    def test_tool_image_keeps_text_identity_and_real_pixels(self):
        for model in ("deepseek", "glm"):
            converted = to_openai_request(image_tool_request(model))
            result = converted["messages"][-1]
            self.assertEqual(result["tool_call_id"], "image_read")
            self.assertEqual(result["content"][0]["text"], "before image")
            self.assertEqual(result["content"][-1]["text"], "after image")
            self.assertEqual(result["content"][1]["image_url"]["url"], "data:image/png;base64," + PNG)

    def test_image_tool_result_succeeds_in_json_sse_and_token_count(self):
        request = image_tool_request()
        request["tools"] = [{"name": "Read", "input_schema": {"type": "object"}}]
        self.assertEqual(self.client.post("/v1/messages", json=request).status_code, 200)
        streamed = self.client.post("/v1/messages", json={**request, "stream": True})
        self.assertEqual(events(streamed)[-1]["type"], "message_stop")
        counted = self.client.post("/v1/messages/count_tokens", json=request)
        self.assertEqual(counted.status_code, 200)
        self.assertGreater(counted.json["input_tokens"], 0)

    def test_gpt_tool_image_preserves_pixels_and_error_prefix(self):
        request = image_tool_request("GPT-6-Luna")
        request["messages"][-1]["content"][0]["is_error"] = True
        result = to_openai_request(request)["messages"][-1]
        self.assertEqual(result["tool_call_id"], "image_read")
        self.assertEqual(result["content"][0]["text"], "Tool error:\n")
        images = [part for part in result["content"] if part["type"] == "image_url"]
        self.assertEqual(images[0]["image_url"]["url"], "data:image/png;base64," + PNG)

    def test_image_url_file_reference_and_invalid_sources(self):
        request = image_tool_request("GPT-6-Luna")
        content = request["messages"][-1]["content"][0]["content"]
        content[1] = {"type": "image", "source": {"type": "url", "url": "https://example.com/figure.png"}}
        result = to_openai_request(request)["messages"][-1]
        self.assertEqual(result["content"][1]["image_url"]["url"], "https://example.com/figure.png")
        content[1] = {"type": "image", "source": {"type": "file", "file_id": "file_123"}}
        self.assertEqual(self.client.post("/v1/messages", json=request).status_code, 400)
        for source in [{"type": "base64", "media_type": "image/png", "data": "invalid%%%"},
                       {"type": "url", "url": "file:///etc/passwd"}, {}]:
            content[1] = {"type": "image", "source": source}
            self.assertEqual(self.client.post("/v1/messages", json=request).status_code, 400)

    def test_multiple_images_keep_their_pixels_and_order(self):
        request = image_tool_request("deepseek")
        request["messages"][-1]["content"][0]["content"].append(image_block())
        result = to_openai_request(request)["messages"][-1]["content"]
        self.assertEqual(sum(part["type"] == "image_url" for part in result), 2)
        self.assertEqual(result[1], result[-1])

    def test_direct_user_image_and_image_token_estimates(self):
        import random
        def chunk(name, data):
            return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))
        rng = random.Random(4827)
        pixels = b"".join(b"\x00" + rng.randbytes(300) for _ in range(100))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 100, 100, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
        request = {"model": "GPT-6-Luna", "max_tokens": 128, "messages": [{"role": "user", "content": [
            image_block(base64.b64encode(png).decode()), {"type": "text", "text": "Describe this image."}]}]}
        converted = to_openai_request(request)
        self.assertEqual(converted["messages"][0]["content"][0]["type"], "image_url")
        self.assertLess(input_token_count(converted), 2000)

    def test_invalid_upstream_tool_json_is_an_api_error(self):
        self.completion = {"model": "glm", "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
            {"id": "toolu_bad", "function": {"name": "Read", "arguments": "not json"}}
        ]}}]}
        with self.assertLogs("genai-proxy", level="ERROR"):
            response = self.client.post("/v1/messages", json=self.payload)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json["error"]["type"], "api_error")

    def test_bad_inputs_are_not_silently_dropped(self):
        for update in [{"max_tokens": 0}, {"messages": []}, {"messages": [{"role": "user", "content": [{"type": "image", "source": {}}]}]}, {"tool_choice": {"type": "tool", "name": "missing"}}]:
            with self.subTest(update=update):
                response = self.client.post("/v1/messages", json={**self.payload, **update})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["error"]["type"], "invalid_request_error")

    def test_errors_use_anthropic_json_and_sse(self):
        self.complete.side_effect = RuntimeError("model unavailable")
        with self.assertLogs("genai-proxy", level="ERROR"):
            response = self.client.post("/v1/messages", json=self.payload)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json["error"]["message"], "model unavailable")
        self.stream.return_value = iter([{"type": "error", "error": "model unavailable"}])
        with self.assertLogs("genai-proxy", level="ERROR"):
            response = self.client.post("/v1/messages", json={**self.payload, "stream": True})
            result = events(response)
        self.assertEqual(result[-1]["type"], "error")
        self.assertNotIn("message_stop", [e["type"] for e in result])


class SharedBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "main.py"
        spec = importlib.util.spec_from_file_location("genai_test_backend", path)
        cls.backend = importlib.util.module_from_spec(spec)
        with patch.object(sys, "argv", [str(path)]), patch.dict(os.environ, {"GENAI_TOKEN": "test-token"}):
            spec.loader.exec_module(cls.backend)

    def test_upstream_error_does_not_become_empty_success(self):
        response = Mock(status_code=200)
        response.iter_lines.return_value = iter([b'data: {"code":500,"errMsg":"model missing"}'])
        with patch.object(self.backend.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "model missing"):
                self.backend.collect_genai_response([{"role": "user", "content": "hi"}], "glm", 32)

    def test_claude_helpers_and_official_flash_names_resolve(self):
        for model in ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "deepseek-flash"]:
            with self.subTest(model=model):
                self.assertEqual(self.backend.resolve_model(model), ("deepseek-pro", "xinference"))

    def test_final_chunk_content_and_finish_reason_survive(self):
        response = Mock(status_code=200)
        response.iter_lines.return_value = iter([b'data: {"choices":[{"delta":{"content":"last"},"finish_reason":"length"}]}'])
        with patch.object(self.backend.requests, "post", return_value=response):
            collected = self.backend.collect_genai_response([{"role": "user", "content": "hi"}], "glm", 32)
        self.assertEqual(collected["content"], "last")
        self.assertEqual(collected["finish_reason"], "length")

    def test_native_call_arguments_survive_interleaved_sse_fragments(self):
        chunks = [
            {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "first", "function": {"name": "Read", "arguments": '{"file_'}},
                {"index": 1, "id": "second", "function": {"name": "Bash", "arguments": '{"command":"py'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [
                {"index": 1, "function": {"arguments": 'thon3 task.py"}'}},
                {"index": 0, "function": {"arguments": 'path":"notes.txt"}'}}]}, "finish_reason": "tool_calls"}]},
        ]
        upstream = Mock(status_code=200)
        upstream.iter_lines.return_value = iter([b"data: " + json.dumps(chunk).encode() for chunk in chunks])
        with patch.object(self.backend.requests, "post", return_value=upstream):
            result = self.backend.collect_genai_response([{"role": "user", "content": "act"}], "glm", 256)
        self.assertEqual(result["content"], "")
        self.assertEqual([call["id"] for call in result["tool_calls"]], ["first", "second"])
        self.assertEqual(json.loads(result["tool_calls"][0]["function"]["arguments"]), {"file_path": "notes.txt"})
        self.assertEqual(json.loads(result["tool_calls"][1]["function"]["arguments"]), {"command": "python3 task.py"})

    def test_assistant_text_does_not_hide_tool_calls(self):
        result = self.backend.normalize_messages_for_genai([{"role": "assistant", "content": "checking", "tool_calls": [{"id": "toolu_1"}]}])
        self.assertIn("checking", result[0]["content"])
        self.assertIn("toolu_1", result[0]["content"])

    def test_openai_tool_call_array_is_not_returned_as_plain_text(self):
        raw = json.dumps([{"id": "call_run", "type": "function", "function": {
            "name": "Bash", "arguments": {"command": "python3 quicksort.py"}}}])
        calls = self.backend.parse_tool_calls_from_content(raw)
        self.assertEqual(calls[0]["id"], "call_run")
        self.assertEqual(calls[0]["function"]["name"], "Bash")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"command": "python3 quicksort.py"})

    def prepared_tool_request(self, strict=True):
        payload = {"model": "deepseek", "messages": [{"role": "user", "content": "write and run quicksort"}],
                   "tools": [{"type": "function", "function": {"name": "Bash", "parameters": {
                       "type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}]}
        if strict:
            payload["tool_protocol"] = "json"
        return self.backend.prepare_chat_completion(payload)

    @staticmethod
    def collected(content):
        return {"content": content, "reasoning_content": "", "finish_reason": "stop"}

    def test_plain_promise_gets_one_protocol_correction(self):
        responses = [self.collected("I'll write and run it."), self.collected('{"tool_calls":[{"name":"Bash","arguments":{"command":"python3 quicksort.py"}}]}')]
        with patch.object(self.backend, "collect_genai_response", side_effect=responses) as collect:
            response = self.backend.complete_prepared_chat(self.prepared_tool_request())
        self.assertEqual(collect.call_count, 2)
        self.assertEqual(response["choices"][0]["finish_reason"], "tool_calls")
        self.assertIn("Gateway protocol correction", collect.call_args.kwargs["messages"][-1]["content"])

    def test_strict_final_answer_is_unwrapped(self):
        with patch.object(self.backend, "collect_genai_response", return_value=self.collected('{"final":"Finished."}')):
            response = self.backend.complete_prepared_chat(self.prepared_tool_request())
        self.assertEqual(response["choices"][0]["message"]["content"], "Finished.")

    def test_native_call_without_text_is_an_executable_response(self):
        collected = {**self.collected(""), "tool_calls": [{"id": "native_1", "type": "function", "function": {
            "name": "Bash", "arguments": '{"command":"python3 quicksort.py"}'}}], "finish_reason": "tool_calls"}
        with patch.object(self.backend, "collect_genai_response", return_value=collected) as collect:
            response = self.backend.complete_prepared_chat(self.prepared_tool_request())
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(response["choices"][0]["message"]["tool_calls"][0]["id"], "native_1")

    def test_schema_and_forced_choice_are_enforced_before_client_execution(self):
        valid = self.collected('{"tool_calls":[{"name":"Bash","arguments":{"command":"python3 quicksort.py"}}]}')
        for invalid in ['{"tool_calls":[{"name":"Bash","arguments":{}}]}',
                        '{"tool_calls":[{"name":"Bash","arguments":{"command":17}}]}',
                        '{"final":"Done"}']:
            prepared = self.prepared_tool_request()
            prepared["tool_choice"] = "required"
            with patch.object(self.backend, "collect_genai_response", side_effect=[self.collected(invalid), valid]) as collect:
                result = self.backend.complete_prepared_chat(prepared)
            self.assertEqual(collect.call_count, 2)
            self.assertEqual(result["choices"][0]["finish_reason"], "tool_calls")

    def test_strict_history_preserves_result_identity_and_object_arguments(self):
        payload = {"model": "deepseek", "tool_protocol": "json", "tools": [{"type": "function", "function": {
            "name": "Read", "parameters": {"type": "object"}}}], "messages": [
                {"role": "user", "content": "read then summarize"},
                {"role": "assistant", "tool_calls": [{"id": "original_id", "type": "function", "function": {"name": "Read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "original_id", "content": "actual result"}]}
        prepared = self.backend.prepare_chat_completion(payload)
        self.assertIn('"tool_call_id":"original_id"', prepared["messages"][-1]["content"])
        self.assertIn('"name":"Read"', prepared["messages"][-1]["content"])
        calls = json.loads(prepared["messages"][-2]["content"])["tool_calls"]
        self.assertEqual(calls[0]["id"], "original_id")
        self.assertEqual(calls[0]["arguments"], {})

    def test_gpt_tool_result_image_reaches_the_existing_upload_path(self):
        payload = to_openai_request(image_tool_request("GPT-6-Luna"))
        uploaded = {"imageUrl": "https://example.com/uploaded.png", "width": 1, "height": 1}
        with patch.object(self.backend, "upload_image_to_genai", return_value=uploaded) as upload:
            prepared = self.backend.prepare_chat_completion(payload, "test-token")
        self.assertEqual(prepared["image_payload"], uploaded)
        self.assertEqual(upload.call_args.args[0], base64.b64decode(PNG))
        self.assertEqual(upload.call_args.args[2], "image/png")
        self.assertEqual(upload.call_args.args[3], "test-token")
        self.assertNotIn(PNG, json.dumps(prepared["messages"]))
        with patch.object(self.backend, "upload_image_to_genai") as upload:
            prepared = self.backend.prepare_chat_completion(to_openai_request(image_tool_request("deepseek")))
        upload.assert_not_called()
        self.assertIsNone(prepared["image_payload"])
        result = prepared["messages"][-1]
        self.assertEqual(result["role"], "user")
        self.assertIn('"tool_call_id": "image_read"', result["content"][0]["text"])
        pixels = [part for part in result["content"] if part.get("type") == "image_url"]
        self.assertEqual(pixels[0]["image_url"]["url"], "data:image/png;base64," + PNG)
        self.assertNotIn(PNG, result["content"][0]["text"])

    def test_openai_endpoint_enforces_budget_on_the_actual_upstream_prompt(self):
        messages = []
        for index in range(25):
            messages.extend([{"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"https://example.com/old-{index}.png"}}]},
                             {"role": "assistant", "content": f"Recorded observation {index}"}])
        newest = "data:image/png;base64," + PNG
        messages.extend([{"role": "user", "content": "Inspect the new image."},
                         {"role": "assistant", "tool_calls": [{"id": "latest", "function": {"name": "Read", "arguments": "{}"}}]},
                         {"role": "tool", "tool_call_id": "latest", "content": [{"type": "image_url", "image_url": {"url": newest}}]}])
        upstream = Mock(status_code=200)
        upstream.iter_lines.return_value = iter([b'data: {"choices":[{"delta":{"content":"observed"},"finish_reason":"stop"}]}'])
        with patch.dict(self.backend.SERVER_SETTINGS, {"GENAI_MAX_IMAGES": "5"}), patch.object(self.backend.requests, "post", return_value=upstream) as post:
            response = self.backend.app.test_client().post("/v1/chat/completions", json={"model": "deepseek", "messages": messages})
        self.assertEqual(response.status_code, 200)
        forwarded = post.call_args.kwargs["json"]["messages"]
        urls = [part["image_url"]["url"] for message in forwarded if isinstance(message.get("content"), list)
                for part in message["content"] if part.get("type") == "image_url"]
        self.assertEqual(len(urls), 5)
        self.assertIn(newest, urls)
        self.assertIn("Recorded observation 0", json.dumps(forwarded))

    def test_json_final_cannot_ask_again_instead_of_running(self):
        for text in ["Want me to run this benchmark in your repo?", "我来运行这个程序。", "I'll run a check now."]:
            with self.subTest(text=text):
                responses = [self.collected(json.dumps({"final": text})), self.collected('{"tool_calls":[{"name":"Bash","arguments":{"command":"python3 quicksort.py"}}]}')]
                with patch.object(self.backend, "collect_genai_response", side_effect=responses) as collect:
                    response = self.backend.complete_prepared_chat(self.prepared_tool_request())
                self.assertEqual(collect.call_count, 2)
                self.assertEqual(response["choices"][0]["finish_reason"], "tool_calls")

    def test_execution_guard_allows_blockers_explanations_and_completed_turns(self):
        self.backend.validate_final_execution("Python is missing. Which interpreter should I use?", True)
        self.backend.validate_final_execution("Want me to run the example?", False)
        messages = [{"role": "user", "content": "write and run quicksort"},
                    {"role": "assistant", "tool_calls": [{"id": "run_1", "function": {"name": "Bash"}}]},
                    {"role": "tool", "tool_call_id": "run_1", "content": "OK"}]
        tools = [{"function": {"name": "Bash"}}]
        self.assertFalse(self.backend.execution_is_pending(messages, tools))
        messages[-1]["content"] = "Tool error:\ncommand failed"
        self.assertTrue(self.backend.execution_is_pending(messages, tools))

    def test_malformed_tool_response_never_becomes_successful_prose(self):
        with patch.object(self.backend, "collect_genai_response", return_value=self.collected("I'll run it.")) as collect:
            with self.assertRaisesRegex(RuntimeError, "protocol correction"):
                self.backend.complete_prepared_chat(self.prepared_tool_request())
        self.assertEqual(collect.call_count, 2)

    def test_legacy_openai_prose_does_not_require_an_envelope(self):
        with patch.object(self.backend, "collect_genai_response", return_value=self.collected("hello")) as collect:
            response = self.backend.complete_prepared_chat(self.prepared_tool_request(strict=False))
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(response["choices"][0]["message"]["content"], "hello")

    def test_tool_contract_preserves_system_instructions_in_one_message(self):
        result = self.backend.build_tool_calling_messages([
            {"role": "system", "content": "caller instructions"},
            {"role": "user", "content": "read"},
        ], [{"type": "function", "function": {"name": "Read"}}], "auto")
        self.assertEqual(sum(m["role"] == "system" for m in result), 1)
        self.assertIn("caller instructions", result[0]["content"])
        self.assertIn('"tool_calls"', result[0]["content"])


if __name__ == "__main__":
    unittest.main()
