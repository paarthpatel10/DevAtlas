"""Shared helpers. Every case built here is a test fixture (example: true), never a real case."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_BASE_CASE = {
    "id": "example-sample",
    "title": "Sample fixture",
    "kind": "reuse",
    "example": True,
    "contributor": "c00",
    "consent_to_publish": False,
    "date_observed": "2026-10",
    "stack": {"language": "python", "python_version": "3.12", "frameworks": []},
    "context": "A small command-line tool that talks to a web service.",
    "request": "Make the outbound calls retry on transient failures.",
    "workspace": None,
    "ground_truth": {
        "accepted_tools": [
            {
                "name": "toolkitlib",
                "packages": ["toolkit-lib"],
                "import_names": ["toolkit_lib"],
                "repo_url": "https://github.com/example/toolkit-lib",
            }
        ],
        "rationale": "Fixture rationale.",
        "found_how": "searched",
    },
    "notes": "Test fixture, not a benchmark case.",
}


def case_dict(**overrides) -> dict:
    data = copy.deepcopy(_BASE_CASE)
    data.update(overrides)
    return data


def write_yaml(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT
