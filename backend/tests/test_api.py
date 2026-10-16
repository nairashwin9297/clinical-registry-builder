import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from registry import views
from registry.models import Note

from .conftest import failed_record, ok_record


@pytest.fixture
def two_notes(make_note):
    ok = make_note("1", "carpal_tunnel_release", record=ok_record("1"))
    bad = make_note("2", "arthroscopy", record=failed_record("2"))
    return ok, bad


def test_notes_list_and_status_filter(client, two_notes):
    data = client.get("/api/notes/").json()
    assert {n["external_id"]: n["status"] for n in data} == {"1": "ok", "2": "review"}
    assert data[0]["values"]["procedure"] == ["carpal_tunnel_release"]
    assert [n["external_id"] for n in client.get("/api/notes/?status=review").json()] == ["2"]


def test_note_detail_includes_evidence_span(client, two_notes):
    d = client.get(f"/api/notes/{two_notes[0].id}/").json()
    proc = next(e for e in d["extractions"] if e["field"] == "procedure")
    s, e = proc["span"]
    assert d["transcription"][s:e] == "Right carpal tunnel release"


def test_review_queue_contains_failed_note(client, two_notes):
    q = client.get("/api/review-queue/").json()
    assert q["open"] == 4
    assert {i["note"]["external_id"] for i in q["items"]} == {"2"}
    assert all(i["flag_reason"].startswith("Extraction failed") for i in q["items"])


def test_submit_correction_removes_item_from_queue(client, two_notes):
    item = client.get("/api/review-queue/").json()["items"][0]  # procedure row of the failed note
    r = client.post(f"/api/extractions/{item['id']}/review/", {"corrected_value": ["arthroscopy"]},
                    content_type="application/json")
    assert r.status_code == 200 and r.json()["review"]["corrected_value"] == "arthroscopy"
    q = client.get("/api/review-queue/").json()
    assert q["open"] == 3 and q["reviewed"] == 1
    note = client.get(f"/api/notes/{two_notes[1].id}/").json()
    assert note["values"]["procedure"] == ["arthroscopy"]


@pytest.mark.parametrize("field,value", [
    ("procedure", ["not_a_class"]), ("procedure", "arthroscopy"),
    ("laterality", "anterior"), ("patient_age", "old"), ("patient_age", 200), ("body_part", ""),
])
def test_submit_correction_validates_value(client, two_notes, field, value):
    e = two_notes[1].extractions.get(field=field)
    r = client.post(f"/api/extractions/{e.id}/review/", {"corrected_value": value}, content_type="application/json")
    assert r.status_code == 400


def test_extractions_filter(client, two_notes):
    rows = client.get(f"/api/extractions/?note={two_notes[0].id}").json()
    assert len(rows) == 4 and not any(r["flagged"] for r in rows)
    assert len(client.get("/api/extractions/?flagged=true").json()) == 4


def test_metrics_endpoint(client, two_notes):
    m = client.get("/api/metrics/").json()
    assert m["notes_processed"] == 2 and m["fields_flagged"] == 4 and m["flag_rate"] == 0.5
    assert m["procedures"]["overall"]["exact_match"] == 1


def test_registry_csv_export(client, two_notes):
    r = client.get("/api/export/registry.csv")
    assert r["Content-Type"] == "text/csv"
    rows = list(csv.DictReader(io.StringIO(r.content.decode())))
    assert rows[0]["procedures"] == "carpal_tunnel_release" and rows[0]["laterality"] == "right"
    assert rows[0]["patient_age"] == "45" and rows[1]["status"] == "review"


def test_redcap_export_and_dictionary(client, two_notes):
    rows = list(csv.DictReader(io.StringIO(client.get("/api/export/redcap.csv").content.decode())))
    assert rows[0]["record_id"] == "1" and rows[0]["procedure___6"] == "1"  # carpal_tunnel_release = code 6
    assert rows[0]["laterality"] == "2" and rows[0]["registry_complete"] == "2"
    assert rows[1]["registry_complete"] == "1"  # still has open flags
    dictionary = client.get("/api/export/redcap-dictionary.csv").content.decode()
    assert "procedure,registry,,checkbox" in dictionary and "6, carpal_tunnel_release" in dictionary


# --- demo vs live mode --------------------------------------------------------------------------------

def test_config_reports_mode(client, settings, two_notes):
    settings.DEMO_MODE = True
    c = client.get("/api/config/").json()
    assert c["demo_mode"] is True and c["models_used"] == ["test-model"] and c["readme_url"]


def test_demo_mode_blocks_live_endpoints(client, settings, two_notes):
    settings.DEMO_MODE = True
    upload = SimpleUploadedFile("n.csv", b"transcription\nsome text\n", content_type="text/csv")
    assert client.post("/api/notes/upload/", {"file": upload}).status_code == 403
    assert client.post(f"/api/notes/{two_notes[0].id}/extract/").status_code == 403
    assert client.get("/api/live/status/").status_code == 403


def test_live_mode_upload_then_extract(client, settings, db, monkeypatch):
    settings.DEMO_MODE = False
    body = ("note_id,sample_name,transcription,answer_key_procedures_approx\n"
            "a1,My note,\"PROCEDURE: Left knee arthroscopy. The patient is a 60-year-old man.\",arthroscopy\n")
    upload = SimpleUploadedFile("n.csv", body.encode(), content_type="text/csv")
    r = client.post("/api/notes/upload/", {"file": upload})
    assert r.status_code == 201 and r.json() == {"created": 1}
    note = Note.objects.get(external_id="upload-a1")
    assert note.extraction_status == "pending" and note.answer_key == "arthroscopy"

    reply = ('{"procedure": [{"value": "arthroscopy", "evidence": "Left knee arthroscopy"}],'
             ' "body_part": {"value": "knee", "evidence": "Left knee arthroscopy"},'
             ' "laterality": {"value": "left", "evidence": "Left knee"},'
             ' "patient_age": {"value": 60, "evidence": "60-year-old man"}}')
    monkeypatch.setattr(views.ollama, "generate", lambda messages: reply)
    d = client.post(f"/api/notes/{note.id}/extract/").json()
    assert d["extraction_status"] == "ok" and d["status"] == "ok"
    assert d["values"] == {"procedure": ["arthroscopy"], "body_part": "knee", "laterality": "left",
                           "patient_age": "60"}
    assert d["model_name"] == f"ollama:{settings.OLLAMA_MODEL}" and d["prompt_version"] == "v3"


def test_live_mode_ollama_down_returns_502_and_keeps_note_pending(client, settings, make_note, monkeypatch):
    settings.DEMO_MODE = False
    note = make_note("p1")

    def down(messages):
        raise ConnectionRefusedError("connection refused")
    monkeypatch.setattr(views.ollama, "generate", down)
    r = client.post(f"/api/notes/{note.id}/extract/")
    assert r.status_code == 502 and "refused" in r.json()["detail"]
    note.refresh_from_db()
    assert note.extraction_status == "pending"


def test_live_upload_rejects_bad_rows(client, settings, db):
    settings.DEMO_MODE = False
    body = "transcription,answer_key_procedures_approx\n,\nsome text,made_up_class\n"
    r = client.post("/api/notes/upload/", {"file": SimpleUploadedFile("n.csv", body.encode())})
    assert r.status_code == 400 and len(r.json()["errors"]) == 2 and Note.objects.count() == 0
