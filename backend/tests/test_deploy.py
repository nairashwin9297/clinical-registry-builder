"""Phase 5: static export, README results section, production settings."""

import json
import os
import subprocess
import sys

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import RequestFactory

from config.urls import frontend_missing
from registry import extraction_core as core
from registry.models import Note, Review
from registry.readme import current_section, results_markdown
from registry.metrics import compute_metrics
from registry.services import notes_with_extractions

from .conftest import failed_record, ok_record


def test_export_static_writes_demo_files(make_note, tmp_path):
    make_note("1", record=ok_record("1"))
    make_note("2", "arthroscopy", record=failed_record("2"))
    call_command("export_static", out=str(tmp_path))

    config = json.loads((tmp_path / "config.json").read_text())
    assert config["static"] is True and config["demo_mode"] is True and config["live_model"] is None
    assert len(config["data_version"]) == 12
    notes = json.loads((tmp_path / "notes.json").read_text())
    assert [n["external_id"] for n in notes] == ["1", "2"]
    assert notes[1]["raw_outputs"] == ["{", "{"]  # failed note keeps raw replies for the UI
    assert json.loads((tmp_path / "metrics.json").read_text())["fields_flagged"] == 4
    for name in ["registry.csv", "redcap.csv", "redcap-dictionary.csv"]:
        assert (tmp_path / name).read_text().startswith(("note_id", "record_id", "Variable"))


def test_export_static_refuses_when_reviews_exist(make_note, tmp_path):
    note = make_note("2", record=failed_record("2"))
    Review.objects.create(extraction=note.extractions.first(), corrected_value="knee")
    with pytest.raises(CommandError, match="fresh import"):
        call_command("export_static", out=str(tmp_path))


def test_data_version_changes_with_data(make_note, tmp_path):
    make_note("1", record=ok_record("1"))
    call_command("export_static", out=str(tmp_path / "a"))
    make_note("2", record=ok_record("2"))
    call_command("export_static", out=str(tmp_path / "b"))
    version = lambda d: json.loads((tmp_path / d / "config.json").read_text())["data_version"]
    assert version("a") != version("b")


@pytest.mark.django_db
def test_readme_results_section_is_up_to_date():
    """The README's numbers must come from data/results.json. Fix with:
    python manage.py readme_results --write ../README.md"""
    readme = settings.REPO_DIR / "README.md"
    if not (settings.REPO_DIR / "data" / "results.json").exists():
        pytest.skip("data/results.json not present")
    call_command("import_results")
    models = sorted(set(Note.objects.exclude(model_name="").values_list("model_name", flat=True)))
    expected = results_markdown(compute_metrics(notes_with_extractions()), models, core.PROMPT_VERSION)
    assert current_section(readme.read_text(encoding="utf-8")) == expected


def test_debug_false_requires_secret_key():
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    env.update(DEBUG="false", DJANGO_SETTINGS_MODULE="config.settings")
    result = subprocess.run([sys.executable, "-c", "import django; django.setup()"], cwd=settings.BASE_DIR,
                            env=env, capture_output=True, text=True)
    assert result.returncode != 0 and "SECRET_KEY" in result.stderr


def test_root_explains_missing_frontend_build():
    # WhiteNoise serves index.html at "/" when frontend/dist exists; otherwise this view answers.
    resp = frontend_missing(RequestFactory().get("/"))
    assert resp.status_code == 404 and b"npm run build" in resp.content
