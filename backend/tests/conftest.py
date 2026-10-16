import pytest

from registry.models import Note
from registry.services import save_record

NOTE_TEXT = (
    "PROCEDURE: Right carpal tunnel release.\n"
    "HISTORY: The patient is a 45-year-old woman with numbness of the right hand.\n"
    "DESCRIPTION: The transverse carpal ligament was divided."
)


def ok_record(note_id="1", procedures=(("carpal_tunnel_release", "Right carpal tunnel release"),),
              body=("wrist", "carpal tunnel release"), lat=("right", "numbness of the right hand"),
              age=(45, "45-year-old woman"), rejected=()):
    return {"note_id": note_id, "status": "ok", "attempts": 1, "error": None, "raw_outputs": ["{}"],
            "rejected_procedures": [{"value": v, "evidence": e} for v, e in rejected],
            "fields": {"procedure": [{"value": v, "evidence": e} for v, e in procedures],
                       "body_part": {"value": body[0], "evidence": body[1]},
                       "laterality": {"value": lat[0], "evidence": lat[1]},
                       "patient_age": {"value": age[0], "evidence": age[1]}}}


def failed_record(note_id="2"):
    return {"note_id": note_id, "status": "failed", "attempts": 2, "fields": None, "rejected_procedures": [],
            "error": "invalid JSON: Expecting ',' delimiter", "raw_outputs": ["{", "{"]}


@pytest.fixture
def make_note(db):
    def make(external_id="1", answer_key="carpal_tunnel_release", text=NOTE_TEXT, record=None, source="mtsamples"):
        note = Note.objects.create(external_id=external_id, source=source, sample_name=f"Note {external_id}",
                                   transcription=text, answer_key=answer_key)
        if record is not None:
            save_record(note, record, "test-model", "v3")
        return note
    return make
