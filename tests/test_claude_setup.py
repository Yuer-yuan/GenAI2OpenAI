import json
from pathlib import Path
import tempfile
import unittest

from tools.claude_code import claude_command, setup


class ClaudeSetupTests(unittest.TestCase):
    def test_project_configuration_preserves_settings_and_does_not_copy_token(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            target = directory / ".claude" / "settings.local.json"
            target.parent.mkdir()
            target.write_text(json.dumps({"env": {"KEEP_ME": "yes"}, "permissions": {"deny": ["Read(.env)"]}}))
            secret = "test-genai-token-not-for-settings"
            config = {"GENAI_TOKEN": secret, "GENAI_HOST": "127.0.0.1", "GENAI_PORT": "8123"}
            setup(directory, "glm", config)
            setup(directory, "deepseek", config)
            data = json.loads(target.read_text())
            self.assertEqual(data["env"]["KEEP_ME"], "yes")
            self.assertEqual(data["permissions"], {"deny": ["Read(.env)"], "defaultMode": "bypassPermissions"})
            self.assertEqual(data["disableAutoMode"], "disable")
            self.assertTrue(data["skipWebFetchPreflight"])
            self.assertEqual(data["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "deepseek")
            self.assertEqual(data["env"]["CLAUDE_CODE_ENABLE_TODO_TOOLS"], "1")
            self.assertEqual(data["env"]["ANTHROPIC_BASE_URL"], "http://127.0.0.1:8123")
            self.assertEqual(data["env"]["ANTHROPIC_MODEL"], "deepseek")
            self.assertIn("token", data["apiKeyHelper"])
            self.assertNotIn(secret, target.read_text())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual((directory / ".gitignore").read_text().count(".claude/settings.local.json"), 1)

    def test_launcher_defaults_to_full_permissions_even_for_resumed_sessions(self):
        command = claude_command("deepseek", ["--continue"])
        self.assertEqual(command[command.index("--permission-mode") + 1], "bypassPermissions")
        self.assertIn("--continue", command)

    def test_launcher_preserves_an_explicit_permission_mode(self):
        command = claude_command("deepseek", ["--permission-mode", "acceptEdits"])
        self.assertEqual(command.count("--permission-mode"), 1)
        self.assertIn("acceptEdits", command)
        self.assertIn("--permission-mode=plan", claude_command("glm", ["--permission-mode=plan"]))

    def test_setup_preserves_permission_rules_and_explicit_plan_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            target = directory / ".claude" / "settings.local.json"
            target.parent.mkdir()
            rules = {"defaultMode": "plan", "deny": ["Read(.env)"], "ask": ["Bash(git push *)"]}
            target.write_text(json.dumps({"permissions": rules}))
            setup(directory, "glm", {"GENAI_PORT": "8000"}, permission_mode="plan")
            self.assertEqual(json.loads(target.read_text())["permissions"], rules)

    def test_setup_replaces_auto_mode_with_requested_full_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            target = directory / ".claude" / "settings.local.json"
            target.parent.mkdir()
            target.write_text(json.dumps({"permissions": {"defaultMode": "auto", "deny": ["Read(.env)"]}}))
            setup(directory, "deepseek", {"GENAI_PORT": "8000"})
            self.assertEqual(json.loads(target.read_text())["permissions"], {"defaultMode": "bypassPermissions", "deny": ["Read(.env)"]})

    def test_manual_mode_remains_an_explicit_option(self):
        command = claude_command("glm", [], permission_mode="manual")
        self.assertEqual(command[command.index("--permission-mode") + 1], "manual")

    def test_http_bridge_settings_replace_only_managed_proxies(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            setup(directory, "deepseek", {}, http_proxy="http://127.0.0.1:8124")
            target = directory / ".claude" / "settings.local.json"
            data = json.loads(target.read_text())
            self.assertEqual(data["env"]["HTTPS_PROXY"], "http://127.0.0.1:8124")
            self.assertEqual(data["env"]["ALL_PROXY"], "http://127.0.0.1:8124")
            self.assertIn("127.0.0.1", data["env"]["NO_PROXY"])
            setup(directory, "deepseek", {})
            self.assertNotIn("HTTPS_PROXY", json.loads(target.read_text())["env"])

    def test_an_explicit_auto_request_removes_the_local_disable(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            setup(directory, "deepseek", {"GENAI_PORT": "8000"})
            target = directory / ".claude" / "settings.local.json"
            self.assertEqual(json.loads(target.read_text())["disableAutoMode"], "disable")
            setup(directory, "deepseek", {"GENAI_PORT": "8000"}, permission_mode="auto")
            self.assertNotIn("disableAutoMode", json.loads(target.read_text()))
