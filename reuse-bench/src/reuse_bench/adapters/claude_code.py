"""Claude Code adapter: one headless `claude -p` run per call.

Isolation (verified on Claude Code 2.1.322, see the plan's "Decisions" section):
- `--setting-sources project` skips user settings (hooks, plugins enabled there, permissions);
- `--strict-mcp-config --mcp-config <file>` gives exactly the condition's MCP servers;
- `--disable-slash-commands` disables skills and commands;
- `claudeMdExcludes` drops the user-level CLAUDE.md and rules; the workspace CLAUDE.md
  (condition B) still loads;
- `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` disables auto memory;
- the owner's login keeps working. Org-managed plugins cannot be disabled and are recorded per
  run from the `system/init` event.

The event stream is untrusted data: it is parsed, never executed or followed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from reuse_bench.schema import Condition, Limits, RunRecord
from reuse_bench.workspace import ancestor_instruction_files

_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PWD|CREDENTIAL", re.IGNORECASE)
_SECRET_PREFIXES = ("neon_", "gemini")
# Needed for the owner's subscription login when it is provided through the environment.
_KEEP = {"CLAUDE_CODE_OAUTH_TOKEN"}
ENV_SET = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
_STDERR_TAIL = 300


def default_executable() -> str:
    found = shutil.which("claude")
    if found:
        return found
    return str(Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude"))


def claude_md_excludes() -> list[str]:
    home = Path.home().as_posix()
    return [f"{home}/.claude/CLAUDE.md", f"{home}/.claude/rules/**"]


def agent_version(executable: str) -> str | None:
    try:
        out = subprocess.run(
            [executable, "--version"], capture_output=True, timeout=60, check=False
        ).stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return out.strip() or None


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if len(secret) >= 6:
            text = text.replace(secret, "[REDACTED]")
    return text


@dataclass
class ParsedStream:
    events: list[dict] = field(default_factory=list)
    init: dict | None = None
    result: dict | None = None


def parse_stream(stdout: str) -> ParsedStream:
    """Parse stream-json output; non-JSON or truncated lines are skipped."""
    parsed = ParsedStream()
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        parsed.events.append(event)
        if event.get("type") == "system" and event.get("subtype") == "init":
            parsed.init = event
        elif event.get("type") == "result":
            parsed.result = event
    return parsed


def _last_assistant_text(events: list[dict]) -> str:
    for event in reversed(events):
        if event.get("type") != "assistant":
            continue
        blocks = (event.get("message") or {}).get("content") or []
        texts = [
            b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        ]
        if any(texts):
            return "\n".join(texts)
    return ""


def has_transcript(events: list[dict]) -> bool:
    """True when the agent produced at least one assistant message with text or a tool call."""
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" or str(block.get("text") or "").strip():
                return True
    return False


def _status(
    result: dict | None,
    timed_out: bool,
    returncode: int | None,
    stderr: str,
    transcript: bool = False,
) -> tuple[str, str | None]:
    """completed, truncated (turn cap or time limit with a usable transcript) or failed."""
    if timed_out:
        return ("truncated" if transcript else "failed"), "timeout"
    if result is None:
        tail = stderr.strip()[-_STDERR_TAIL:]
        return (
            "failed",
            f"no_result (exit {returncode}): {tail}" if tail else f"no_result (exit {returncode})",
        )
    subtype = result.get("subtype")
    if subtype == "success" and not result.get("is_error"):
        return "completed", None
    if subtype == "error_max_turns":
        return ("truncated" if transcript else "failed"), "max_turns"
    detail = result.get("terminal_reason") or result.get("api_error_status") or ""
    return "failed", f"{subtype}: {detail}".rstrip(": ")


def record_from_stream(
    stdout: str,
    *,
    stderr: str,
    returncode: int | None,
    timed_out: bool,
    started_at: datetime,
    ended_at: datetime,
    agent_version: str | None,
    isolation: dict,
    secrets: list[str],
) -> RunRecord:
    parsed = parse_stream(redact(stdout, secrets))
    stderr = redact(stderr, secrets)
    init = parsed.init or {}
    result = parsed.result
    exit_status, failure_reason = _status(
        result, timed_out, returncode, stderr, has_transcript(parsed.events)
    )
    final = (result or {}).get("result") or _last_assistant_text(parsed.events)
    cost = (result or {}).get("total_cost_usd")
    plugins = [p.get("name") if isinstance(p, dict) else str(p) for p in init.get("plugins") or []]
    servers = [
        {"name": s.get("name"), "status": s.get("status")} if isinstance(s, dict) else {"name": s}
        for s in init.get("mcp_servers") or []
    ]
    return RunRecord(
        agent="claude_code",
        agent_version=init.get("claude_code_version") or agent_version,
        model=init.get("model"),
        events=parsed.events,
        final_message=final,
        exit_status=exit_status,
        failure_reason=failure_reason,
        cost_usd=float(cost) if isinstance(cost, int | float) else None,
        usage=(result or {}).get("usage"),
        num_turns=(result or {}).get("num_turns"),
        permission_denials=(result or {}).get("permission_denials") or [],
        isolation=isolation
        | {
            "active_plugins": plugins,
            "mcp_servers": servers,
            "tools": list(init.get("tools") or []),
            "slash_commands": len(init.get("slash_commands") or []),
            "api_key_source": init.get("apiKeySource"),
            "permission_mode": init.get("permissionMode"),
            "init_seen": parsed.init is not None,
        },
        started_at=started_at,
        ended_at=ended_at,
    )


def _kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


class ClaudeCodeAdapter:
    name = "claude_code"
    instruction_filename = "CLAUDE.md"

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or default_executable()

    def build_command(
        self, prompt: str, mcp_config_path: Path, limits: Limits, condition: Condition
    ) -> list[str]:
        allowed = [*limits.allowed_tools, *condition.extra_allowed_tools]
        cmd = [
            self.executable,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--max-turns",
            str(limits.max_turns),
            "--no-session-persistence",
            "--permission-mode",
            limits.permission_mode,
            "--allowedTools",
            ",".join(allowed),
            "--setting-sources",
            "project",
            "--strict-mcp-config",
            "--mcp-config",
            str(mcp_config_path),
            "--disable-slash-commands",
            "--settings",
            json.dumps({"claudeMdExcludes": claude_md_excludes()}),
        ]
        if limits.model:
            cmd += ["--model", limits.model]
        return cmd

    def child_env(self, base: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
        env: dict[str, str] = {}
        removed: list[str] = []
        for name, value in base.items():
            secret = _SECRET_NAME.search(name) or name.lower().startswith(_SECRET_PREFIXES)
            if secret and name not in _KEEP:
                removed.append(name)
            else:
                env[name] = value
        return env | ENV_SET, removed

    def run(
        self, workspace_dir: Path, prompt: str, condition: Condition, limits: Limits
    ) -> RunRecord:
        env, removed = self.child_env(os.environ)
        secrets = [os.environ[name] for name in removed]
        fd, mcp_name = tempfile.mkstemp(prefix="rb-mcp-", suffix=".json")
        mcp_path = Path(mcp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"mcpServers": condition.mcp_servers}, fh)
        cmd = self.build_command(prompt, mcp_path, limits, condition)
        isolation = {
            "flags": [arg for arg in cmd[3:] if arg != str(mcp_path)],
            "env_set": dict(ENV_SET),
            "env_removed": sorted(removed),
            "claude_md_excludes": claude_md_excludes(),
            "ancestor_instruction_files": ancestor_instruction_files(workspace_dir),
            "condition_mcp_servers": sorted(condition.mcp_servers),
        }
        version = agent_version(self.executable)
        started = datetime.now(UTC)
        stdout = stderr = b""
        timed_out = False
        returncode: int | None = None
        try:
            popen_kwargs: dict = {}
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen(
                cmd,
                cwd=workspace_dir,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **popen_kwargs,
            )
            try:
                stdout, stderr = proc.communicate(timeout=limits.timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_tree(proc)
                try:
                    stdout, stderr = proc.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    stdout, stderr = b"", b""
            returncode = proc.returncode
        except FileNotFoundError:
            stderr = f"agent executable not found: {self.executable}".encode()
        finally:
            mcp_path.unlink(missing_ok=True)
        return record_from_stream(
            stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            returncode=returncode,
            timed_out=timed_out,
            started_at=started,
            ended_at=datetime.now(UTC),
            agent_version=version,
            isolation=isolation,
            secrets=secrets,
        )
