"""Business logic shared by the import command, live mode and the API views."""

from django.db import transaction
from django.utils import timezone

from . import extraction_core as core
from .models import Extraction, Note


@transaction.atomic
def save_record(note, record, model_name, prompt_version):
    """Store one extraction record (Colab results.json entry or live Ollama result) for a note.

    Replaces any earlier extractions for the note (their reviews are deleted with them).
    """
    note.extractions.all().delete()
    note.extraction_status = "ok" if record["status"] == "ok" else "failed"
    note.extraction_error = record.get("error") or ""
    note.attempts = record.get("attempts", 0)
    note.raw_outputs = record.get("raw_outputs", [])
    note.model_name = model_name
    note.prompt_version = prompt_version
    note.extracted_at = timezone.now()
    note.save()
    # Flags are computed by the same shared rules the notebook preview uses.
    rows = core.build_extractions(record, note.transcription)
    Extraction.objects.bulk_create(Extraction(note=note, **row) for row in rows)


def needs_review(extraction):
    return extraction.flagged and not hasattr(extraction, "review")


def final_values(note):
    """The registry row for a note: model answers, with human corrections applied where reviewed."""
    out = {"procedure": [], "body_part": "", "laterality": "", "patient_age": ""}
    procedures = set()
    for e in note.extractions.all():
        review = getattr(e, "review", None)
        if e.field == "procedure":
            if review is not None:
                procedures.update(c for c in review.corrected_value.split("|") if c)
            elif e.value in core.PROCEDURE_OPTIONS:
                procedures.add(e.value)  # unreviewed invalid values are left out of the registry
        else:
            out[e.field] = review.corrected_value if review is not None else e.value
    out["procedure"] = [c for c in core.CLASS_IDS if c in procedures]  # stable class order
    return out


def note_status(note):
    """'pending' (not extracted), 'review' (has unreviewed flags) or 'ok'."""
    if note.extraction_status == "pending":
        return "pending"
    return "review" if any(needs_review(e) for e in note.extractions.all()) else "ok"


def notes_with_extractions():
    return Note.objects.prefetch_related("extractions__review")


def find_spans(extraction, note_text):
    """Character span of the evidence quote in the note, for highlighting (or None)."""
    if not extraction.evidence_quote:
        return None
    _, span = core.locate_quote(extraction.evidence_quote, note_text)
    return list(span) if span else None


def validate_correction(field, value):
    """Check a reviewer's corrected value. Returns the string to store or raises ValueError."""
    if field == "procedure":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError("procedure correction must be a list of class IDs (empty = not performed)")
        bad = [v for v in value if v not in core.PROCEDURE_OPTIONS]
        if bad:
            raise ValueError(f"not allowed procedure classes: {bad}")
        return "|".join(c for c in core.CLASS_IDS if c in value)
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError("corrected value must be text")
    v = str(value).strip().lower()
    if field == "laterality":
        if v not in core.LATERALITY_OPTIONS:
            raise ValueError(f"laterality must be one of {core.LATERALITY_OPTIONS}")
        return v
    if field == "patient_age":
        if v == core.NOT_MENTIONED:
            return v
        if not v.isdigit() or not 0 <= int(v) <= 120:
            raise ValueError("age must be a whole number from 0 to 120, or 'not mentioned'")
        return str(int(v))
    if field == "body_part":
        if not v or len(v) > 100:
            raise ValueError("body part must be 1-100 characters")
        return v
    raise ValueError(f"unknown field {field}")
