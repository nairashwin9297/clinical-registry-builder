import csv
import json

import pytest
from django.conf import settings
from django.core.management import call_command

from registry.models import Extraction, Note

from .conftest import NOTE_TEXT, failed_record, ok_record


@pytest.fixture
def files(tmp_path):
    notes = tmp_path / "notes.csv"
    with open(notes, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["note_id", "sample_name", "description", "transcription", "keywords",
                    "answer_key_procedures_approx"])
        w.writerow([1, "Carpal Tunnel Release", "", NOTE_TEXT, "carpal tunnel release", "carpal_tunnel_release"])
        w.writerow([2, "Shoulder Arthroscopy", "", NOTE_TEXT, "", "arthroscopy"])
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"model": "google/gemma-3-4b-it", "prompt_version": "v3",
                                   "results": [ok_record(1), failed_record(2)]}))
    return str(notes), str(results)


@pytest.mark.django_db
def test_import_keeps_failed_note_in_review_queue(files):
    call_command("import_results", notes=files[0], results=files[1])
    assert Note.objects.count() == 2
    failed = Note.objects.get(external_id="2")
    assert failed.extraction_status == "failed" and "invalid JSON" in failed.extraction_error
    rows = failed.extractions.all()
    assert rows.count() == 4 and all(e.flagged for e in rows)
    ok = Note.objects.get(external_id="1")
    assert ok.extraction_status == "ok" and ok.model_name == "google/gemma-3-4b-it" and ok.prompt_version == "v3"


@pytest.mark.django_db
def test_import_is_repeatable(files):
    call_command("import_results", notes=files[0], results=files[1])
    call_command("import_results", notes=files[0], results=files[1])
    assert Note.objects.count() == 2 and Extraction.objects.count() == 8


@pytest.mark.django_db
def test_import_real_project_data():
    """The committed data/notes.csv + data/results.json import cleanly; note 2309 is the failed one."""
    data = settings.REPO_DIR / "data"
    if not (data / "results.json").exists():
        pytest.skip("data/results.json not present")
    call_command("import_results")
    assert Note.objects.count() == 100
    assert list(Note.objects.filter(extraction_status="failed").values_list("external_id", flat=True)) == ["2309"]
    assert Extraction.objects.filter(note__external_id="2309", flagged=True).count() == 4
