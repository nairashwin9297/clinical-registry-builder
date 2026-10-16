import csv
import io
import uuid
from functools import wraps

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from . import exports, ollama
from . import extraction_core as core
from .metrics import compute_metrics
from .models import Extraction, Note, Review
from .services import (final_values, find_spans, needs_review, note_status, notes_with_extractions,
                       save_record, validate_correction)

EXCERPT_CONTEXT = 300  # characters of note text shown around the evidence in the review queue


# ---------------------------------------------------------------------------------------------------
# Serialization helpers (plain dicts keep the response shape easy to read)
# ---------------------------------------------------------------------------------------------------

def review_dict(review):
    if review is None:
        return None
    return {"corrected_value": review.corrected_value, "timestamp": review.timestamp.isoformat()}


def extraction_dict(e, note_text):
    return {"id": e.id, "field": e.field, "value": e.value, "evidence_quote": e.evidence_quote,
            "flagged": e.flagged, "flag_reason": e.flag_reason, "match_type": e.match_type,
            "span": find_spans(e, note_text), "review": review_dict(getattr(e, "review", None))}


def note_summary(n):
    flagged = [e for e in n.extractions.all() if e.flagged]
    return {"id": n.id, "external_id": n.external_id, "source": n.source, "sample_name": n.sample_name,
            "extraction_status": n.extraction_status, "status": note_status(n), "values": final_values(n),
            "flags": len(flagged), "open_flags": sum(needs_review(e) for e in flagged),
            "answer_key": n.answer_key_list}


def note_detail_dict(n):
    return {**note_summary(n), "description": n.description, "transcription": n.transcription,
            "keywords": n.keywords, "extraction_error": n.extraction_error, "attempts": n.attempts,
            "model_name": n.model_name, "prompt_version": n.prompt_version,
            "extracted_at": n.extracted_at.isoformat() if n.extracted_at else None,
            # Raw replies help explain a failure; for successful notes they'd only add page weight.
            "raw_outputs": n.raw_outputs if n.extraction_status == "failed" else [],
            "extractions": [extraction_dict(e, n.transcription) for e in n.extractions.all()]}


def excerpt(text, span):
    """A window of the note around the evidence span, with the span offsets shifted to match."""
    if span is None:
        return {"text": text[:2 * EXCERPT_CONTEXT], "highlight": None,
                "truncated_start": False, "truncated_end": len(text) > 2 * EXCERPT_CONTEXT}
    start, end = max(0, span[0] - EXCERPT_CONTEXT), min(len(text), span[1] + EXCERPT_CONTEXT)
    return {"text": text[start:end], "highlight": [span[0] - start, span[1] - start],
            "truncated_start": start > 0, "truncated_end": end < len(text)}


def live_only(view):
    """Block live-extraction endpoints in the hosted demo."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if settings.DEMO_MODE:
            return Response({"detail": "Live extraction is disabled in demo mode (DEMO_MODE=true)."}, status=403)
        return view(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------------------------------

def config_dict():
    models = sorted({m for m in Note.objects.exclude(model_name="").values_list("model_name", flat=True)})
    return {
        "demo_mode": settings.DEMO_MODE,
        "static": False,
        "readme_url": settings.README_URL,
        "fields": core.FIELDS,
        "procedure_options": core.PROCEDURE_OPTIONS,
        "laterality_options": core.LATERALITY_OPTIONS,
        "prompt_version": core.PROMPT_VERSION,
        "models_used": models,
        "notes_total": Note.objects.count(),
        "notes_by_source": {s: Note.objects.filter(source=s).count() for s, _ in Note.SOURCES},
        "live_model": None if settings.DEMO_MODE else settings.OLLAMA_MODEL,
    }


@api_view(["GET"])
def config(request):
    return Response(config_dict())


@api_view(["GET"])
def notes_list(request):
    notes = [note_summary(n) for n in notes_with_extractions()]
    status = request.query_params.get("status")
    if status:
        notes = [n for n in notes if n["status"] == status]
    return Response(notes)


@api_view(["GET"])
def note_detail(request, pk):
    return Response(note_detail_dict(get_object_or_404(notes_with_extractions(), pk=pk)))


@api_view(["GET"])
def extractions_list(request):
    qs = Extraction.objects.select_related("note", "review")
    if "note" in request.query_params:
        qs = qs.filter(note_id=request.query_params["note"])
    if request.query_params.get("flagged") in ("true", "1"):
        qs = qs.filter(flagged=True)
    return Response([{**extraction_dict(e, e.note.transcription), "note_id": e.note_id} for e in qs])


@api_view(["GET"])
def review_queue(request):
    """Flagged extractions. By default only those not yet reviewed."""
    qs = Extraction.objects.filter(flagged=True).select_related("note", "review")
    if request.query_params.get("include_reviewed") not in ("true", "1"):
        qs = qs.filter(review__isnull=True)
    items = []
    for e in qs:
        d = extraction_dict(e, e.note.transcription)
        d["note"] = {"id": e.note.id, "external_id": e.note.external_id, "sample_name": e.note.sample_name,
                     "extraction_status": e.note.extraction_status}
        d["excerpt"] = excerpt(e.note.transcription, d["span"])
        items.append(d)
    return Response({"items": items, "open": Extraction.objects.filter(flagged=True, review__isnull=True).count(),
                     "reviewed": Review.objects.count()})


@api_view(["GET"])
def metrics(request):
    return Response(compute_metrics(notes_with_extractions()))


def _csv_response(content, filename):
    resp = HttpResponse(content, content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@api_view(["GET"])
def export_registry(request):
    return _csv_response(exports.registry_csv(notes_with_extractions()), "registry.csv")


@api_view(["GET"])
def export_redcap(request):
    return _csv_response(exports.redcap_csv(notes_with_extractions()), "redcap_import.csv")


@api_view(["GET"])
def export_redcap_dictionary(request):
    return _csv_response(exports.redcap_dictionary_csv(), "redcap_data_dictionary.csv")


# ---------------------------------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------------------------------

@api_view(["POST"])
@parser_classes([JSONParser])
def submit_review(request, pk):
    """Body: {"corrected_value": ...}. For procedure rows, a list of class IDs (empty = not performed)."""
    e = get_object_or_404(Extraction, pk=pk)
    if "corrected_value" not in request.data:
        return Response({"detail": "corrected_value is required"}, status=400)
    try:
        value = validate_correction(e.field, request.data["corrected_value"])
    except ValueError as err:
        return Response({"detail": str(err)}, status=400)
    review, _ = Review.objects.update_or_create(extraction=e, defaults={"corrected_value": value})
    return Response({"id": e.id, "review": review_dict(review)})


# ---------------------------------------------------------------------------------------------------
# Live mode (DEMO_MODE=false): upload notes, run extraction with a local Ollama model
# ---------------------------------------------------------------------------------------------------

@api_view(["GET"])
@live_only
def live_status(request):
    return Response(ollama.status())


@api_view(["POST"])
@live_only
@parser_classes([MultiPartParser])
def upload_notes(request):
    """CSV upload. Required column: transcription. Optional: note_id, sample_name, description,
    answer_key_procedures_approx ("|"-separated class IDs, used to score the model)."""
    f = request.FILES.get("file")
    if f is None:
        return Response({"detail": "Upload a CSV file in the 'file' field."}, status=400)
    try:
        reader = csv.DictReader(io.StringIO(f.read().decode("utf-8-sig")))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as err:
        return Response({"detail": f"Could not read CSV: {err}"}, status=400)
    if "transcription" not in (reader.fieldnames or []):
        return Response({"detail": "CSV needs a 'transcription' column."}, status=400)
    if not rows or len(rows) > settings.MAX_UPLOAD_NOTES:
        return Response({"detail": f"CSV must have 1-{settings.MAX_UPLOAD_NOTES} rows."}, status=400)

    errors, new = [], []
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        text = (r.get("transcription") or "").strip()
        key = [c for c in (r.get("answer_key_procedures_approx") or "").split("|") if c.strip()]
        bad = [c for c in key if c.strip() not in core.PROCEDURE_OPTIONS]
        ext_id = f"upload-{(r.get('note_id') or '').strip() or uuid.uuid4().hex[:8]}"
        if not text:
            errors.append(f"row {i}: empty transcription")
        elif bad:
            errors.append(f"row {i}: unknown answer-key classes {bad}")
        elif Note.objects.filter(external_id=ext_id).exists() or ext_id in {n.external_id for n in new}:
            errors.append(f"row {i}: note_id already exists ({ext_id})")
        else:
            new.append(Note(external_id=ext_id, source="upload", transcription=text,
                            sample_name=(r.get("sample_name") or "").strip()[:255],
                            description=(r.get("description") or "").strip(),
                            answer_key="|".join(c.strip() for c in key)))
    if errors:
        return Response({"detail": "Nothing imported. Fix these rows:", "errors": errors}, status=400)
    with transaction.atomic():
        Note.objects.bulk_create(new)
    return Response({"created": len(new)}, status=201)


@api_view(["POST"])
@live_only
def run_extraction(request, pk):
    """Run extraction on one note now (synchronous; the UI calls this note by note)."""
    note = get_object_or_404(Note, pk=pk)
    record = core.extract_note(note.external_id, note.transcription, ollama.generate)
    if record["status"] == "failed" and (record["error"] or "").startswith("generation error"):
        # Ollama itself failed (not running, model missing...). Don't store it as a model failure.
        return Response({"detail": record["error"]}, status=502)
    save_record(note, record, f"ollama:{settings.OLLAMA_MODEL}", core.PROMPT_VERSION)
    return Response(note_detail_dict(get_object_or_404(notes_with_extractions(), pk=pk)))
