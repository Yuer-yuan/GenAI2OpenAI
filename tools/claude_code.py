"""Configure and launch Claude Code against this project's Messages endpoint."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from dotenv import dotenv_values

PROJECT = Path(__file__).resolve().parents[1]


def configuration():
    values = {key: value for key, value in dotenv_values(PROJECT / ".env").items() if value is not None}
    values.update({key: value for key, value in os.environ.items() if key.startswith("GENAI_")})
    return values


def server_url(config):
    host = config.get("GENAI_HOST", "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{config.get('GENAI_PORT', '5000')}"


def setup(directory, model, config, permission_mode="bypassPermissions", http_proxy=None):
    target = directory.resolve() / ".claude" / "settings.local.json"
    settings = json.loads(target.read_text()) if target.exists() else {}
    env = settings.setdefault("env", {})
    bypass = ",".join(filter(None, [os.environ.get("NO_PROXY", os.environ.get("no_proxy", "")), "localhost", "127.0.0.1", "::1"]))
    env.update({
        "ANTHROPIC_BASE_URL": server_url(config),
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "ANTHROPIC_AUTH_TOKEN": "",
        "ANTHROPIC_API_KEY": "",
        "ENABLE_TOOL_SEARCH": "false",
        "MAX_THINKING_TOKENS": "0",
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "8192",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_ENABLE_TODO_TOOLS": "1",
        "NO_PROXY": bypass,
        "no_proxy": bypass,
    })
    proxy_keys = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")
    old_proxy = env.pop("GENAI_MANAGED_HTTP_PROXY", None)
    if http_proxy:
        env.update({key: http_proxy for key in proxy_keys})
        env["GENAI_MANAGED_HTTP_PROXY"] = http_proxy
    elif old_proxy:
        for key in proxy_keys:
            if env.get(key) == old_proxy:
                del env[key]
    settings["apiKeyHelper"] = shlex.join([sys.executable, str(Path(__file__).resolve()), "token"])
    # The domain preflight uses Anthropic's service rather than this gateway;
    # this machine cannot reach it. Fetching and summarization still use the
    # real WebFetch implementation and the configured model.
    settings["skipWebFetchPreflight"] = True
    # The launcher also passes this explicitly: recent Claude Code versions
    # ignore bypassPermissions when it comes only from project settings.
    permissions = settings.setdefault("permissions", {})
    permissions["defaultMode"] = "default" if permission_mode == "manual" else permission_mode
    if permission_mode == "auto":
        settings.pop("disableAutoMode", None)
    else:
        settings["disableAutoMode"] = "disable"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".{os.getpid()}.tmp")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
        json.dump(settings, file, indent=2, ensure_ascii=False)
        file.write("\n")
    os.replace(temporary, target)
    target.chmod(0o600)
    ignore = directory.resolve() / ".gitignore"
    existing = ignore.read_text() if ignore.exists() else ""
    rule = ".claude/settings.local.json"
    if rule not in existing.splitlines():
        ignore.write_text(existing + ("\n" if existing and not existing.endswith("\n") else "") + rule + "\n")
    return target


def ensure_server(config):
    base = server_url(config)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def healthy():
        try:
            with opener.open(base + "/health", timeout=1) as response:
                return json.load(response).get("status") == "ok"
        except (OSError, ValueError):
            return False

    if healthy():
        try:
            with opener.open(urllib.request.Request(base + "/v1/messages", method="OPTIONS"), timeout=2):
                return
        except urllib.error.HTTPError as exc:
            raise RuntimeError("An older server is running. Restart start.command to enable /v1/messages.") from exc
    logs = PROJECT / ".logs"
    logs.mkdir(exist_ok=True)
    with (logs / "server.log").open("a") as logfile:
        process = subprocess.Popen([sys.executable, str(PROJECT / "main.py")], cwd=PROJECT,
                                   env=dict(os.environ), stdin=subprocess.DEVNULL,
                                   stdout=logfile, stderr=logfile, start_new_session=True)
    for _ in range(180):
        if healthy():
            return
        if process.poll() is not None:
            break
        time.sleep(0.25)
    raise RuntimeError(f"Server did not start; see {logs / 'server.log'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("token", help="Print the local GenAI token for Claude Code's apiKeyHelper")
    for command in ("setup", "run"):
        sub = commands.add_parser(command)
        sub.add_argument("--directory", type=Path, default=Path.cwd())
        sub.add_argument("--model", choices=["glm", "deepseek"], default="deepseek")
        sub.add_argument("--permission-mode", choices=["bypassPermissions", "manual", "acceptEdits", "plan", "dontAsk", "auto"], default="bypassPermissions")
        if command == "run":
            sub.add_argument("claude_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    config = configuration()
    token = config.get("GENAI_TOKEN") or os.environ.get("GENAI_TOKEN")
    if args.command == "token":
        if not token:
            raise SystemExit("Set GENAI_TOKEN in the project's .env first")
        print(token)
        return
    if args.command == "run" and not shutil.which("claude"):
        raise SystemExit("Claude Code is not installed or is missing from PATH")
    if __package__:
        from .proxy_bridge import ensure_http_proxy
    else:
        from proxy_bridge import ensure_http_proxy
    http_proxy = ensure_http_proxy(PROJECT)
    target = setup(args.directory, args.model, config, args.permission_mode, http_proxy=http_proxy)
    print(f"Project settings: {target}", flush=True)
    if args.command == "setup":
        return
    if not token:
        raise SystemExit("Set GENAI_TOKEN in the project's .env first")
    ensure_server(config)
    os.chdir(args.directory.resolve())
    extra = args.claude_args
    if extra[:1] == ["--"]:
        extra = extra[1:]
    env = dict(os.environ)
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(name, None)
    os.execvpe("claude", claude_command(args.model, extra, args.permission_mode), env)


def claude_command(model, extra, permission_mode="bypassPermissions"):
    command = ["claude", "--model", model]
    # An explicit flag overrides a resumed session's saved auto mode.
    if not any(arg == "--permission-mode" or arg.startswith("--permission-mode=") for arg in extra):
        command.extend(["--permission-mode", permission_mode])
    return [*command, *extra]


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
