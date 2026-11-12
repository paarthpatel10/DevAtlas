"""Blind human judging: CSV export with hidden conditions, validated import, agreement.

The export hides the condition and the run id. The code-to-run key and the stored judgments live
under runs/judging/ (git-ignored). Two judges per row; disagreements are marked `disputed` and
never resolved by the harness.
"""

from __future__ import annotations

import csv
import json
import random
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from reuse_bench.loading import load_cases, load_conditions
from reuse_bench.runner import finished_run_dirs, load_meta
from reuse_bench.schema import B_INSTRUCTION, AutoScore, Case, Judgment
from reuse_bench.scoring import first_edit_index, load_events

JUDGING_COLUMNS = [
    "code",
    "case_kind",
    "context",
    "request",
    "rationale",
    "agent_proposal",
    "diff_summary",
    "suitable_tool_surfaced",
    "tool_adopted",
    "unneeded_dependency",
    "comment",
]
JUDGE_FIELDS = ("suitable_tool_surfaced", "tool_adopted", "unneeded_dependency")
REUSE_FIELDS = ("suitable_tool_surfaced", "tool_adopted")
CONTROL_FIELDS = ("unneeded_dependency",)
NOT_APPLICABLE = "n/a"
MAX_TEXT = 1500
MAX_JUDGES = 2
_YES = {"yes", "y", "true"}
_NO = {"no", "n", "false"}


class JudgingError(Exception):
    """Export or import could not be completed; the message lists every problem."""


@dataclass(frozen=True)
class Resolution:
    status: str  # agreed | disputed | pending
    suitable_tool_surfaced: bool | None = None
    tool_adopted: bool | None = None
    unneeded_dependency: bool | None = None


def default_paths(root: Path) -> tuple[Path, Path, Path]:
    base = root / "runs" / "judging"
    return base / "judging.csv", base / "key.json", base / "judgments"


def csv_safe(cell: str) -> str:
    """Stop spreadsheet apps from treating a cell as a formula."""
    return "'" + cell if cell[:1] in ("=", "+", "-", "@") else cell


def blind_text(text: str, terms: list[str]) -> str:
    for term in sorted({t for t in terms if t}, key=len, reverse=True):
        text = re.sub(re.escape(term), "[tool]", text, flags=re.IGNORECASE)
    return text


def condition_terms(root: Path) -> list[str]:
    terms: list[str] = []
    for _, condition in load_conditions(root / "conditions"):
        terms += list(condition.mcp_servers)
        if condition.external_tool:
            terms.append(condition.external_tool.name)
    return terms


def _blind(text: str, terms: list[str]) -> str:
    text = text.replace(B_INSTRUCTION, "[instruction]")
    text = re.sub(r"mcp__[\w-]+", "[tool]", text)
    text = re.sub(r"CLAUDE(\.local)?\.md", "[project file]", text, flags=re.IGNORECASE)
    return blind_text(text, terms)


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + " [...]"


def _pre_edit_text(events: list[dict]) -> str:
    stop = first_edit_index(events)
    texts = []
    for event in events if stop is None else events[:stop]:
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text") or ""))
    return "\n".join(texts)


def diff_summary(diff: str, score: AutoScore) -> str:
    files: dict[str, list[int]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = target[2:] if target.startswith("b/") else None
            if current:
                files.setdefault(current, [0, 0])
        elif line.startswith("--- "):
            source = line[4:].strip()
            if source.startswith("a/"):
                current = source[2:]
                files.setdefault(current, [0, 0])
        elif current and line.startswith("+"):
            files[current][0] += 1
        elif current and line.startswith("-"):
            files[current][1] += 1
    lines = [f"{path}: +{add} -{rem}" for path, (add, rem) in sorted(files.items())]
    lines = lines or ["No file changes."]
    lines.append("Added packages: " + (", ".join(score.added_packages) or "none"))
    lines.append("New third-party imports: " + (", ".join(score.new_imports) or "none"))
    return "\n".join(lines)


def _row(case: Case, run_dir: Path, score: AutoScore, terms: list[str]) -> dict[str, str]:
    events = load_events(run_dir)
    final = (run_dir / "final_message.txt").read_text(encoding="utf-8", errors="replace")
    diff = (run_dir / "diff.patch").read_text(encoding="utf-8", errors="replace")
    proposal = (
        "Before the first code edit:\n"
        + (_clip(_pre_edit_text(events)) or "(no text)")
        + "\n\nFinal message:\n"
        + (_clip(final) or "(no text)")
    )
    reuse = case.kind == "reuse"
    return {
        "case_kind": case.kind,
        "context": case.context.strip(),
        "request": case.request.strip(),
        "rationale": case.ground_truth.rationale.strip(),
        "agent_proposal": _blind(proposal, terms),
        "diff_summary": _blind(diff_summary(diff, score), terms),
        "suitable_tool_surfaced": "" if reuse else NOT_APPLICABLE,
        "tool_adopted": "" if reuse else NOT_APPLICABLE,
        "unneeded_dependency": NOT_APPLICABLE if reuse else "",
        "comment": "",
    }


def export_judging(
    root: Path, seed: int, out_csv: Path, key_path: Path, include_examples: bool = False
) -> int:
    if key_path.exists():
        raise JudgingError(
            f"{key_path} already exists; a judging round is in progress. Move it away to start "
            "a new round."
        )
    cases = {case.id: case for _, case in load_cases(root / "cases")}
    terms = condition_terms(root)
    rows: list[tuple[str, str, dict[str, str]]] = []
    missing_scores = []
    for run_dir in finished_run_dirs(root / "runs"):
        meta = load_meta(run_dir)
        if meta.pilot or (meta.example and not include_examples):
            continue
        score_path = run_dir / "auto_score.json"
        if not score_path.exists():
            missing_scores.append(meta.run_id)
            continue
        score = AutoScore.model_validate_json(score_path.read_text(encoding="utf-8"))
        case = cases.get(meta.case_id)
        if not score.needs_judging or case is None:
            continue
        rows.append((meta.run_id, case.kind, _row(case, run_dir, score, terms)))
    if missing_scores:
        raise JudgingError(
            "runs without auto_score.json (run `reuse-bench score` first): "
            + ", ".join(missing_scores)
        )

    random.Random(seed).shuffle(rows)
    key: dict[str, dict[str, str]] = {}
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=JUDGING_COLUMNS)
        writer.writeheader()
        for run_id, kind, row in rows:
            code = "R" + secrets.token_hex(3).upper()
            while code in key:
                code = "R" + secrets.token_hex(3).upper()
            key[code] = {"run_id": run_id, "kind": kind}
            writer.writerow({col: csv_safe(value) for col, value in ({"code": code} | row).items()})
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(key, indent=2), encoding="utf-8")
    return len(rows)


def _parse_answer(raw: str | None) -> bool | None | str:
    value = (raw or "").strip().lstrip("'").strip().lower()
    if value in _YES:
        return True
    if value in _NO:
        return False
    if value in ("", NOT_APPLICABLE):
        return None
    return "invalid"


def import_judgments(csv_path: Path, judge: str, key_path: Path, store_dir: Path) -> int:
    if not re.fullmatch(r"j\d{2,}", judge):
        raise JudgingError(f"judge code '{judge}' must look like j01")
    key = json.loads(key_path.read_text(encoding="utf-8"))
    others = {p.stem for p in store_dir.glob("j*.json")} - {judge} if store_dir.exists() else set()
    if len(others) >= MAX_JUDGES:
        raise JudgingError(
            f"two judges ({', '.join(sorted(others))}) are already stored; "
            f"rows are judged by two judges only"
        )

    errors: list[str] = []
    judgments: list[Judgment] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            code = (row.get("code") or "").strip()
            if code not in key:
                errors.append(f"row {line_no}: unknown code '{code}'")
                continue
            kind = key[code]["kind"]
            required = REUSE_FIELDS if kind == "reuse" else CONTROL_FIELDS
            values: dict[str, bool | None] = {}
            for field_name in JUDGE_FIELDS:
                answer = _parse_answer(row.get(field_name))
                if answer == "invalid":
                    errors.append(f"row {line_no} ({code}): {field_name} must be yes or no")
                elif field_name in required and answer is None:
                    errors.append(f"row {line_no} ({code}): {field_name} is required")
                elif field_name not in required and answer is not None:
                    errors.append(
                        f"row {line_no} ({code}): {field_name} does not apply to {kind} cases"
                    )
                values[field_name] = answer if isinstance(answer, bool) else None
            judgments.append(
                Judgment(
                    code=code, judge=judge, comment=(row.get("comment") or "").strip(), **values
                )
            )
    if errors:
        raise JudgingError("\n".join(errors))
    store_dir.mkdir(parents=True, exist_ok=True)
    payload = [j.model_dump() for j in judgments]
    (store_dir / f"{judge}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(judgments)


def load_judgments(store_dir: Path) -> dict[str, list[Judgment]]:
    by_code: dict[str, list[Judgment]] = {}
    if not store_dir.exists():
        return by_code
    for path in sorted(store_dir.glob("j*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            judgment = Judgment.model_validate(item)
            by_code.setdefault(judgment.code, []).append(judgment)
    return by_code


def resolve(judgments_by_code: dict[str, list[Judgment]]) -> dict[str, Resolution]:
    resolved: dict[str, Resolution] = {}
    for code, judgments in judgments_by_code.items():
        if len(judgments) < MAX_JUDGES:
            resolved[code] = Resolution("pending")
            continue
        answers = [tuple(getattr(j, f) for f in JUDGE_FIELDS) for j in judgments]
        if len(set(answers)) > 1:
            resolved[code] = Resolution("disputed")
        else:
            resolved[code] = Resolution("agreed", *answers[0])
    return resolved


def resolutions_by_run(root: Path) -> dict[str, Resolution]:
    """Resolution per run id for the current judging round (empty if none exported)."""
    _, key_path, store_dir = default_paths(root)
    if not key_path.exists():
        return {}
    key = json.loads(key_path.read_text(encoding="utf-8"))
    resolved = resolve(load_judgments(store_dir))
    return {
        entry["run_id"]: resolved.get(code, Resolution("pending")) for code, entry in key.items()
    }
