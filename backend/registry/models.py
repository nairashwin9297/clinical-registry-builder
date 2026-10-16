from django.db import models

from .extraction_core import FIELDS


class Note(models.Model):
    """One clinical note plus the outcome of running extraction on it."""

    SOURCES = [("mtsamples", "MTSamples (imported)"), ("upload", "Uploaded (live mode)")]
    STATUSES = [("pending", "Not extracted yet"), ("ok", "Extracted"), ("failed", "Extraction failed")]

    external_id = models.CharField(max_length=64, unique=True)  # MTSamples row index, or upload id
    source = models.CharField(max_length=16, choices=SOURCES)
    sample_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    transcription = models.TextField()
    keywords = models.TextField(blank=True)
    # Approximate ground truth derived from sample_name + keywords in Phase 1; "|"-separated class IDs.
    answer_key = models.CharField(max_length=255, blank=True)

    extraction_status = models.CharField(max_length=16, choices=STATUSES, default="pending")
    extraction_error = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    model_name = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    raw_outputs = models.JSONField(default=list, blank=True)  # kept for debugging failed/odd replies
    extracted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    @property
    def answer_key_list(self):
        return [c for c in self.answer_key.split("|") if c]

    def __str__(self):
        return f"{self.external_id}: {self.sample_name}"


class Extraction(models.Model):
    """One extracted answer. A note has one row per procedure class plus one per other field."""

    note = models.ForeignKey(Note, related_name="extractions", on_delete=models.CASCADE)
    field = models.CharField(max_length=32, choices=[(f, f) for f in FIELDS])
    value = models.CharField(max_length=255, blank=True)
    evidence_quote = models.TextField(blank=True)
    flagged = models.BooleanField(default=False)
    flag_reason = models.CharField(max_length=500, blank=True)
    match_type = models.CharField(max_length=10, blank=True)  # "exact" / "near" / "" (no match checked)

    class Meta:
        ordering = ["note_id", "id"]


class Review(models.Model):
    """A human correction of one flagged extraction. Re-submitting replaces it."""

    extraction = models.OneToOneField(Extraction, related_name="review", on_delete=models.CASCADE)
    # For procedure rows: "|"-separated class IDs that replace this row ("" = not performed).
    corrected_value = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now=True)
