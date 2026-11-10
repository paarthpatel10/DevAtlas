import json
from pathlib import Path

from app.schemas.snapshot import CuratedEntry, curated_by_stem, load_snapshot
from tests.factories import FIXTURES_DIR


def test_load_snapshot_applies_curation_before_validation(tmp_path: Path):
    data = json.loads((FIXTURES_DIR / "acme__jobs.json").read_text(encoding="utf-8"))
    data["category"] = "llm_agents_mcp"  # a slug from an older category set
    path = tmp_path / "acme__jobs.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    curated = curated_by_stem([CuratedEntry(full_name="Acme/Jobs", category="security")])
    snap = load_snapshot(path, curated)
    assert (snap.category, snap.featured) == ("security", False)


def test_load_snapshot_without_curation_keeps_stored_labels():
    snap = load_snapshot(FIXTURES_DIR / "acme__jobs.json")
    assert (snap.category, snap.featured) == ("backend", True)


def test_curated_by_stem_uses_snapshot_filenames():
    entries = [CuratedEntry(full_name="vercel/next.js", category="full_stack", featured=True)]
    assert list(curated_by_stem(entries)) == ["vercel__next.js"]
