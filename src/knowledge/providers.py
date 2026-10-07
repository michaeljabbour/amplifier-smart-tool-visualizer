"""Which model answers, and calling it. Loaded only by the model-backed capabilities.

No vendor SDK is needed: Anthropic, OpenAI and Ollama are called over HTTP with the
standard library, and `--complete-cmd` hands the call to any program (your host's model).

Order, first that applies wins:

1. An explicit choice: a `complete` function (library), `--complete-cmd`, `--provider`,
   then KNOWLEDGE_COMPLETE_CMD / KNOWLEDGE_PROVIDER.
2. The agent harness this runs inside (Claude Code, Codex, Amplifier, or KNOWLEDGE_HOST):
   the agent is the model, so the call stops with `host_model` and names the deterministic
   route. No API key is billed, even if one is set. KNOWLEDGE_HOST=none turns this off.
3. Whichever API key is set, Anthropic first. This is billed to that key.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .errors import MODEL_CALL, SETUP, USAGE, ToolError

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-5.5", "ollama": "mistral-openorca"}
PROVIDERS = tuple(DEFAULT_MODELS)

HOST_MARKERS = (
    ("Codex", ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX", "CODEX_CI")),
    ("Amplifier", ("AMPLIFIER_SESSION_ID",)),
    ("Claude Code", ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")),
)
# Harnesses that export no marker to the commands they run: found by a parent process whose
# program (or the script it runs) has this name. Amplifier's shell tool passes no session
# variable, so this is how a command run by an Amplifier agent knows where it is.
HOST_PROGRAMS = (("Amplifier", "amplifier"),)

Complete = Callable[[str, str], str]


@dataclass
class Route:
    kind: str  # function, command, anthropic, openai, ollama
    model: str = ""
    command: str = ""
    why: str = ""

    def describe(self) -> str:
        if self.kind == "command":
            return f"your command ({self.command})"
        if self.kind == "function":
            return "the function you passed"
        return f"{self.kind} {self.model}"


def detect_host() -> str | None:
    declared = os.environ.get("KNOWLEDGE_HOST", "").strip()
    if declared:
        return None if declared.lower() == "none" else declared
    for name, keys in HOST_MARKERS:
        if any(os.environ.get(k) for k in keys):
            return name
    return _host_from_parents()


def _parent_commands(limit: int = 12) -> list[str]:
    """The command lines of this process's ancestors, nearest first. Empty where `ps` is missing."""
    if os.name != "posix" or not shutil.which("ps"):
        return []
    out, pid = [], os.getppid()
    for _ in range(limit):
        if pid <= 1:
            break
        try:
            line = subprocess.run(["ps", "-o", "ppid=,command=", "-p", str(pid)], capture_output=True,
                                  text=True, timeout=2, check=False).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            break
        parent, _, command = line.partition(" ")
        if not parent.strip().isdigit():
            break
        out.append(command.strip())
        pid = int(parent)
    return out


def _host_from_parents() -> str | None:
    for command in _parent_commands():
        words = command.split()[:2]  # the program, or the interpreter and its script
        names = {os.path.basename(w) for w in words}
        for host, program in HOST_PROGRAMS:
            if program in names:
                return host
    return None


def resolve(provider: str | None = None, model: str | None = None, complete_cmd: str | None = None,
            complete: Complete | None = None, *, deterministic_route: str = "") -> Route:
    """Choose who answers, or raise a ToolError that says exactly what to set."""
    if complete is not None:
        return Route("function", why="passed in")
    complete_cmd = complete_cmd or os.environ.get("KNOWLEDGE_COMPLETE_CMD")
    if complete_cmd:
        return Route("command", command=complete_cmd, why="--complete-cmd")
    provider = (provider or os.environ.get("KNOWLEDGE_PROVIDER") or "").strip().lower()
    model = model or os.environ.get("KNOWLEDGE_MODEL") or ""
    if provider:
        if provider not in PROVIDERS:
            raise ToolError("usage", f"Unknown provider \"{provider}\".",
                            hint="Use anthropic, openai or ollama, or pass --complete-cmd.", exit_code=USAGE)
        _check_key(provider)
        return Route(provider, model or DEFAULT_MODELS[provider], why="chosen")
    host = detect_host()
    if host:
        raise ToolError(
            "host_model",
            f"Running inside {host}: the agent's own model does this step, so no API key is billed.",
            hint=(deterministic_route or "Use the deterministic route shown in this capability's --help.")
            + " To spend an API key on purpose, add --provider anthropic|openai|ollama.",
            exit_code=SETUP)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return Route("anthropic", model or DEFAULT_MODELS["anthropic"], why="ANTHROPIC_API_KEY is set")
    if os.environ.get("OPENAI_API_KEY"):
        return Route("openai", model or DEFAULT_MODELS["openai"], why="OPENAI_API_KEY is set")
    raise ToolError(
        "provider_not_configured",
        "This capability is model-backed and no model is set up.",
        hint="Set ANTHROPIC_API_KEY or OPENAI_API_KEY, run a local model with --provider ollama, or "
        "route the call to your own model with --complete-cmd 'program'. "
        + (deterministic_route or ""),
        exit_code=SETUP)


def _check_key(provider: str) -> None:
    env = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(provider)
    if env and not os.environ.get(env):
        raise ToolError("provider_not_configured", f"The {provider} provider needs {env}.",
                        hint=f"Set {env}, or choose another route (--provider ollama, --complete-cmd).",
                        exit_code=SETUP)


def call(route: Route, system: str, prompt: str, *, complete: Complete | None = None,
         max_tokens: int = 4096, timeout: float = 300.0) -> str:
    """One model call. Raises ToolError(model_call_failed, exit 4) on any failure."""
    try:
        if route.kind == "function":
            assert complete is not None
            return complete(system, prompt)
        if route.kind == "command":
            return _command(route.command, system, prompt, timeout)
        if route.kind == "anthropic":
            data = _post("https://api.anthropic.com/v1/messages",
                         {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                         {"model": route.model, "max_tokens": max_tokens, "system": system,
                          "messages": [{"role": "user", "content": prompt}]}, timeout)
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        if route.kind == "openai":
            base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            data = _post(f"{base}/chat/completions", {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                         {"model": route.model, "messages": [{"role": "system", "content": system},
                                                             {"role": "user", "content": prompt}]}, timeout)
            return data["choices"][0]["message"]["content"] or ""
        if route.kind == "ollama":
            base = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            if not base.startswith("http"):
                base = "http://" + base
            data = _post(f"{base}/api/chat", {}, {"model": route.model, "stream": False,
                                                  "messages": [{"role": "system", "content": system},
                                                               {"role": "user", "content": prompt}]}, timeout)
            return data.get("message", {}).get("content", "")
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure becomes one clear error
        raise ToolError("model_call_failed", f"The model call to {route.describe()} failed: {exc}",
                        hint="Check the key, the model name and the network, then run again.",
                        exit_code=MODEL_CALL) from None
    raise ToolError("usage", f"Unknown route {route.kind}.", exit_code=USAGE)


def _post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed provider URLs
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from None


def _command(command: str, system: str, prompt: str, timeout: float) -> str:
    argv = shlex.split(command)
    if not argv or not shutil.which(argv[0]) and not os.path.exists(argv[0]):
        raise ToolError("missing_prerequisite", f"The --complete-cmd program \"{argv[0] if argv else ''}\" "
                        "was not found.", hint="Give the full path, or check it with: knowledge doctor "
                        "--complete-cmd '...'", exit_code=SETUP)
    proc = subprocess.run(argv, input=json.dumps({"system": system, "prompt": prompt}), capture_output=True,
                          text=True, timeout=timeout)
    if proc.returncode != 0:
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise RuntimeError(f"the command exited {proc.returncode}")
    return proc.stdout


def extract_json(reply: str):
    """Find the JSON value in a model's reply (fenced or bare). Raises ValueError when there is none."""
    text = reply.strip()
    if "```" in text:
        for block in text.split("```")[1::2]:
            block = block.strip()
            if block.startswith("json"):
                block = block[4:]
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
    # try the outermost value first: whichever bracket opens earliest
    pairs = sorted((("[", "]"), ("{", "}")), key=lambda p: (text.find(p[0]) == -1, text.find(p[0])))
    for opener, closer in pairs:
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON found in the reply")


def ask_json(route: Route, system: str, prompt: str, *, complete: Complete | None = None, check=None):
    """Call, parse JSON, run `check` (raises ValueError on a bad shape); repair once, then fail."""
    reply = call(route, system, prompt, complete=complete)
    try:
        value = extract_json(reply)
        return check(value) if check else value
    except ValueError as first:
        repair = (prompt + "\n\nYour previous reply could not be used: " + str(first)
                  + ". Reply again with only the JSON, in exactly the format asked for.")
        reply = call(route, system, repair, complete=complete)
        try:
            value = extract_json(reply)
            return check(value) if check else value
        except ValueError as second:
            raise ToolError("reply_invalid", f"The model's reply was still unusable after one repair: {second}.",
                            hint="Run again, or try another model with --model.", exit_code=MODEL_CALL) from None
