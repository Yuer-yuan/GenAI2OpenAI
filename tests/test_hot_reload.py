"""Exercise real worker reloads without credentials or upstream API requests."""

import json
from http.client import HTTPException
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request


PROJECT = Path(__file__).resolve().parents[1]


class HotReloadTests(unittest.TestCase):
    def test_code_and_env_reload_but_generated_files_do_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("main.py", "anthropic_compat.py", "web_search.py"):
                shutil.copyfile(PROJECT / name, root / name)
            (root / "utility").symlink_to(PROJECT / "utility", target_is_directory=True)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            config = root / ".env"
            config.write_text(f"GENAI_HOST=127.0.0.1\nGENAI_PORT={port}\nGENAI_RELOAD=1\nGENAI_LOG_LEVEL=WARNING\nGENAI_TOKEN=\n")
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("GENAI_", "WERKZEUG_"))}
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def health():
                with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    return json.load(response)

            with (root / "server.log").open("w+") as logfile:
                process = subprocess.Popen([sys.executable, str(root / "main.py")], cwd=root,
                                           env=env, stdout=logfile, stderr=logfile, start_new_session=True)

                def wait_for(predicate):
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        try:
                            value = health()
                            if predicate(value):
                                return value
                        except (OSError, ValueError, HTTPException):
                            pass
                        if process.poll() is not None:
                            break
                        time.sleep(0.1)
                    logfile.flush()
                    self.fail("Server did not reload as expected: " + (root / "server.log").read_text()[-2000:])

                try:
                    initial = wait_for(lambda value: value["runtime"]["reload"])
                    time.sleep(0.8)  # Allow the worker's first watch scan.
                    source = root / "main.py"
                    original = source.read_text()
                    edited = original.replace('return jsonify({"status": "ok",',
                                              'return jsonify({"revision": "changed", "status": "ok",', 1)
                    self.assertNotEqual(original, edited)
                    source.write_text(edited)
                    changed = wait_for(lambda value: value.get("revision") == "changed"
                                       and value["runtime"]["pid"] != initial["runtime"]["pid"])
                    time.sleep(0.8)
                    config.write_text(config.read_text().replace("GENAI_LOG_LEVEL=WARNING", "GENAI_LOG_LEVEL=ERROR"))
                    configured = wait_for(lambda value: value["runtime"]["log_level"] == "ERROR"
                                          and value["runtime"]["pid"] != changed["runtime"]["pid"])
                    generated = root / "temp" / "generated.py"
                    generated.parent.mkdir()
                    generated.write_text("# first version\n")
                    time.sleep(0.8)
                    generated.write_text("# next version\n")
                    time.sleep(1.2)
                    self.assertEqual(health()["runtime"]["pid"], configured["runtime"]["pid"],
                                     (root / "server.log").read_text()[-2000:])
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
