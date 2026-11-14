"""Claude Code adapter tests. The real `claude` binary is never executed."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from reuse_bench.adapters import claude_code as cc
from reuse_bench.adapters.claude_code import ClaudeCodeAdapter, parse_stream, record_from_stream
from reuse_bench.loading import load_conditions
from reuse_bench.schema import Limits

DATA = Path(__file__).parent / "data"


@pytest.fixture
def conditions(project_root):
    return {c.id: c for _, c in load_conditions(project_root / "conditions")}


@pytest.fixture
def adapter():
    return ClaudeCodeAdapter(executable="claude-test-exe")


def _record(stdout: str, **kwargs):
    now = datetime.now(UTC)
    defaults = dict(
        stderr="",
        returncode=0,
        timed_out=False,
        started_at=now,
        ended_at=now,
        agent_version="2.1.322",
        isolation={},
        secrets=[],
    )
    return record_from_stream(stdout, **(defaults | kwargs))


def test_build_command_has_isolation_flags(adapter, conditions, tmp_path):
    cmd = adapter.build_command("Do it", tmp_path / "mcp.json", Limits(), conditions["A"])
    assert cmd[:3] == ["claude-test-exe", "-p", "Do it"]
    joined = " ".join(cmd)
    for flag in (
        "--output-format stream-json",
        "--verbose",
        "--max-turns 30",
        "--no-session-persistence",
        "--permission-mode dontAsk",
        "--setting-sources project",
        "--strict-mcp-config",
        "--disable-slash-commands",
    ):
        assert flag in joined
    assert cmd[cmd.index("--mcp-config") + 1] == str(tmp_path / "mcp.json")
    settings = json.loads(cmd[cmd.index("--settings") + 1])
    home = Path.home().as_posix()
    assert settings == {
        "claudeMdExcludes": [f"{home}/.claude/CLAUDE.md", f"{home}/.claude/rules/**"]
    }
    allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
    assert "WebSearch" in allowed and "WebFetch" in allowed and "Bash(uv *)" in allowed
    assert "--model" not in cmd


def test_command_identical_for_a_and_b(adapter, conditions, tmp_path):
    a = adapter.build_command("Do it", tmp_path / "m.json", Limits(), conditions["A"])
    b = adapter.build_command("Do it", tmp_path / "m.json", Limits(), conditions["B"])
    assert a == b


def test_condition_extra_tools_and_model_are_added(adapter, conditions, tmp_path):
    c = conditions["C"].model_copy(update={"extra_allowed_tools": ["mcp__checker"]})
    cmd = adapter.build_command("x", tmp_path / "m.json", Limits(model="haiku"), c)
    assert cmd[cmd.index("--allowedTools") + 1].endswith(",mcp__checker")
    assert cmd[cmd.index("--model") + 1] == "haiku"


def test_child_env_scrubs_secrets(adapter):
    base = {
        "PATH": "/usr/bin",
        "GITHUB_TOKEN": "ghp_secretvalue123",
        "neon_db": "postgres://u:p@h/db",
        "gemini": "AIzaSecret",
        "ANTHROPIC_API_KEY": "sk-ant-secret",
        "MY_PASSWORD": "hunter22",
    }
    env, removed = adapter.child_env(base)
    assert env["PATH"] == "/usr/bin"
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert sorted(removed) == [
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "MY_PASSWORD",
        "gemini",
        "neon_db",
    ]
    assert not any(v in env.values() for v in ("ghp_secretvalue123", "sk-ant-secret"))


def test_parse_stream_ok():
    parsed = parse_stream((DATA / "stream_ok.jsonl").read_text(encoding="utf-8"))
    assert len(parsed.events) == 5
    assert parsed.init["model"] == "claude-test-model"
    assert parsed.result["total_cost_usd"] == 0.0123


def test_record_from_stream_ok():
    rec = _record((DATA / "stream_ok.jsonl").read_text(encoding="utf-8"))
    assert rec.exit_status == "completed"
    assert rec.failure_reason is None
    assert rec.model == "claude-test-model"
    assert rec.cost_usd == 0.0123
    assert rec.num_turns == 3
    assert rec.final_message == "Done. Added app/retry.py."
    assert rec.isolation["active_plugins"] == ["cc-plugin-sec-default", "cc-plugin-telemetry"]
    assert rec.isolation["tools"] == ["Read", "Edit", "Write", "Bash", "WebSearch", "WebFetch"]
    assert rec.isolation["api_key_source"] == "none"


def test_truncated_stream_is_failed_not_crash():
    rec = _record(
        (DATA / "stream_truncated.jsonl").read_text(encoding="utf-8"),
        returncode=1,
        stderr="boom",
    )
    assert rec.exit_status == "failed"
    assert rec.failure_reason.startswith("no_result")
    assert len(rec.events) == 1


ASSISTANT_LINE = json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "Working on it."}]}}
)
MAX_TURNS_LINE = json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True})


def test_max_turns_without_transcript_is_failed():
    rec = _record(MAX_TURNS_LINE)
    assert (rec.exit_status, rec.failure_reason) == ("failed", "max_turns")


def test_max_turns_with_transcript_is_truncated():
    rec = _record(ASSISTANT_LINE + "\n" + MAX_TURNS_LINE)
    assert (rec.exit_status, rec.failure_reason) == ("truncated", "max_turns")
    assert rec.final_message == "Working on it."


def test_timeout_with_transcript_is_truncated():
    rec = _record(ASSISTANT_LINE + "\n", timed_out=True, returncode=None)
    assert (rec.exit_status, rec.failure_reason) == ("truncated", "timeout")


def test_timeout_without_transcript_is_failed():
    rec = _record("", timed_out=True, returncode=None)
    assert (rec.exit_status, rec.failure_reason) == ("failed", "timeout")


def test_tool_call_alone_counts_as_transcript():
    tool = json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}}
    )
    assert _record(tool + "\n" + MAX_TURNS_LINE).exit_status == "truncated"


def test_crash_and_login_error_stay_failed_even_with_transcript():
    crash = _record(ASSISTANT_LINE + "\n", returncode=1, stderr="Segmentation fault")
    assert crash.exit_status == "failed" and crash.failure_reason.startswith("no_result")
    login = json.dumps(
        {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 401}
    )
    assert _record(ASSISTANT_LINE + "\n" + login).exit_status == "failed"


def test_success_with_is_error_is_failed():
    line = json.dumps(
        {"type": "result", "subtype": "success", "is_error": True, "terminal_reason": "api_error"}
    )
    rec = _record(line)
    assert rec.exit_status == "failed"
    assert "api_error" in rec.failure_reason


def test_missing_cost_is_none():
    line = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "ok"})
    assert _record(line).cost_usd is None


def test_secrets_redacted_from_events_and_stderr():
    line = json.dumps(
        {
            "type": "result",
            "subtype": "error_during_execution",
            "is_error": True,
            "x": "TOPSECRET99",
        }
    )
    rec = _record(line, stderr="token TOPSECRET99 failed", secrets=["TOPSECRET99"])
    assert "TOPSECRET99" not in json.dumps(rec.events)
    rec2 = _record("", returncode=1, stderr="token TOPSECRET99 failed", secrets=["TOPSECRET99"])
    assert "TOPSECRET99" not in rec2.failure_reason


def test_missing_executable_is_failed_run(conditions, tmp_path):
    adapter = ClaudeCodeAdapter(executable=str(tmp_path / "no-such-claude.exe"))
    rec = adapter.run(tmp_path, "x", conditions["A"], Limits())
    assert rec.exit_status == "failed"
    assert "not found" in rec.failure_reason


def test_run_timeout_kills_and_fails(conditions, tmp_path, monkeypatch):
    adapter = ClaudeCodeAdapter(executable=sys.executable)
    monkeypatch.setattr(
        adapter,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    monkeypatch.setattr(cc, "agent_version", lambda exe: "test")
    started = datetime.now(UTC)
    rec = adapter.run(tmp_path, "x", conditions["A"], Limits(timeout_s=1))
    assert (rec.exit_status, rec.failure_reason) == ("failed", "timeout")
    assert (datetime.now(UTC) - started).total_seconds() < 30
