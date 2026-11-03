import json
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from ddgs.exceptions import DDGSException

from anthropic_compat import create_anthropic_blueprint, to_openai_request
from web_search import _seal, result_text, run_server_tools, search_web


def completion(content=None, calls=None):
    message = {"content": content}
    if calls:
        message["tool_calls"] = calls
    return {"model": "deepseek", "choices": [{"message": message, "finish_reason": "tool_calls" if calls else "stop"}]}


def call(name="web_search"):
    return {"id": "call_search", "type": "function", "function": {"name": name, "arguments": '{"query":"Python documentation"}'}}


def payload():
    return to_openai_request({"model": "deepseek", "max_tokens": 128,
        "messages": [{"role": "user", "content": "Search Python documentation"}],
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]})


RESULT = {"type": "web_search_result", "title": "Python docs", "url": "https://docs.python.org/",
          "snippet": "The Python documentation", "encrypted_content": "test-opaque-content"}


class WebSearchTests(unittest.TestCase):
    def test_search_fields_and_domain_filters(self):
        rows = [{"title": "Python docs", "href": "https://docs.python.org/", "body": "Official &amp; current"},
                {"title": "Unrelated", "href": "https://python.org.evil.test/", "body": "Python"}]
        with patch("web_search.DDGS") as engine:
            engine.return_value.text.return_value = rows
            results = search_web("Python", allowed_domains=["python.org"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://docs.python.org/")
        self.assertEqual(results[0]["snippet"], "Official & current")
        self.assertIn("site:python.org", engine.return_value.text.call_args.args[0])
        self.assertEqual(set(engine.call_args.kwargs), {"proxy", "timeout"})

    def test_unrelated_results_trigger_provider_fallback(self):
        junk = [{"title": "FasTest Inc. leak testing", "href": "https://www.fastestinc.com/", "body": "Sealing tools"},
                {"title": "Internet Speed Test", "href": "https://fast.com/", "body": "Check internet speed"},
                {"title": "Microsoft login", "href": "https://account.microsoft.com/", "body": "Sign in"}]
        relevant = {"title": "Sorting algorithms: quicksort, mergesort and timsort benchmark", "href": "https://example.com/sorting", "body": "Algorithm performance comparison"}
        with patch("web_search.DDGS") as engine:
            engine.return_value.text.side_effect = [junk, [relevant, relevant]]
            results = search_web("fastest sorting algorithm comparison quicksort mergesort timsort benchmark")
        self.assertEqual([r["url"] for r in results], [relevant["href"]])
        self.assertEqual([c.kwargs["backend"] for c in engine.return_value.text.call_args_list], ["duckduckgo", "yahoo"])

    def test_irrelevant_results_are_not_successful_searches(self):
        with patch("web_search.DDGS") as engine:
            engine.return_value.text.return_value = [{"title": "Microsoft", "href": "https://microsoft.com", "body": "Login"}]
            with self.assertRaisesRegex(RuntimeError, "no usable results"):
                search_web("timsort vs quicksort vs mergesort performance comparison benchmark")

    def test_provider_failure_is_not_fabricated_results(self):
        with patch("web_search.DDGS") as engine:
            engine.return_value.text.side_effect = DDGSException("rate limited")
            with self.assertRaisesRegex(RuntimeError, "no usable results"):
                search_web("Python")

    def test_opaque_result_round_trip_and_old_histories(self):
        result = {"title": "Source", "url": "https://example.com", "snippet": "Actual fetched snippet"}
        wire = {"title": result["title"], "url": result["url"], "encrypted_content": _seal(result)}
        self.assertIn("Actual fetched snippet", result_text(wire))
        wire["encrypted_content"] = "invalid"
        self.assertIn("fetch the source URL", result_text(wire))

    def test_search_is_executed_and_not_returned_as_a_client_tool(self):
        complete = Mock(side_effect=[completion(calls=[call()]), completion("See https://docs.python.org/")])
        with patch("web_search.search_web", return_value=[RESULT]) as search:
            result = run_server_tools(payload(), complete)
        search.assert_called_once()
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(result["choices"][0]["finish_reason"], "stop")
        blocks = result["_anthropic_content_prefix"]
        self.assertEqual([b["type"] for b in blocks], ["server_tool_use", "web_search_tool_result"])
        self.assertEqual(blocks[0]["id"], blocks[1]["tool_use_id"])
        self.assertNotIn("snippet", blocks[1]["content"][0])
        self.assertEqual(result["_server_tool_usage"]["web_search_requests"], 1)
        self.assertEqual(complete.call_args.args[0]["tools"], [])

    def test_client_tools_are_never_executed_by_the_server(self):
        data = payload()
        client_call = call("Bash")
        complete = Mock(return_value=completion(calls=[client_call]))
        with patch("web_search.search_web") as search:
            result = run_server_tools(data, complete)
        search.assert_not_called()
        self.assertEqual(result["choices"][0]["message"]["tool_calls"], [client_call])

    def test_failed_search_returns_a_real_error_block(self):
        complete = Mock(side_effect=[completion(calls=[call()]), completion("Search unavailable")])
        with patch("web_search.search_web", side_effect=RuntimeError("offline")), self.assertLogs("genai-proxy", level="ERROR"):
            result = run_server_tools(payload(), complete)
        self.assertEqual(result["_anthropic_content_prefix"][1]["content"]["error_code"], "unavailable")
        self.assertEqual(result["_server_tool_usage"]["tool_search"], 0)

    def test_search_history_and_mcp_text_results_are_preserved(self):
        request = {"model": "deepseek", "max_tokens": 128, "messages": [
            {"role": "user", "content": "search"},
            {"role": "assistant", "content": [
                {"type": "server_tool_use", "id": "srv_1", "name": "web_search", "input": {"query": "Python"}},
                {"type": "web_search_tool_result", "tool_use_id": "srv_1", "content": [RESULT]},
                {"type": "text", "text": "Here are the sources."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "mcp_1", "content": [
                {"type": "search_result", "source": "https://example.com", "title": "MCP source", "content": [{"type": "text", "text": "Evidence"}]}]}]},
        ]}
        converted = to_openai_request(request)
        self.assertEqual(converted["messages"][2]["tool_call_id"], "srv_1")
        self.assertIn("https://docs.python.org/", converted["messages"][2]["content"])
        self.assertIn("Evidence", converted["messages"][-1]["content"])

    def test_stream_contains_server_blocks_and_search_usage(self):
        complete = Mock(side_effect=[completion(calls=[call()]), completion("Python docs")])
        app = Flask(__name__)
        app.register_blueprint(create_anthropic_blueprint(complete, Mock()))
        request = {"model": "deepseek", "max_tokens": 128, "stream": True,
                   "messages": [{"role": "user", "content": "search"}],
                   "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]}
        with patch("web_search.search_web", return_value=[RESULT]):
            response = app.test_client().post("/v1/messages", json=request)
            events = [json.loads(line[6:]) for line in response.data.decode().splitlines() if line.startswith("data: ")]
        starts = [e["content_block"]["type"] for e in events if e["type"] == "content_block_start"]
        self.assertEqual(starts, ["server_tool_use", "web_search_tool_result", "text"])
        self.assertEqual(events[-2]["usage"]["server_tool_use"]["web_search_requests"], 1)
        self.assertEqual(events[-1]["type"], "message_stop")
