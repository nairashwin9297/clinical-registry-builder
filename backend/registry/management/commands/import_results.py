"""Import data/notes.csv and data/results.json (from the Colab notebook) into the database.

    python manage.py import_results [--notes PATH] [--results PATH]

Re-running replaces the imported MTSamples notes and their extractions (and any reviews of them).
With --if-empty it does nothing when notes already exist (used by the Docker image on start-up, so
restarting the container keeps your reviews).
Failed extractions (e.g. invalid JSON after the retry) are imported as failed notes whose fields are
all flagged, so they land in the review queue instead of being dropped.
"""

import csv
import json
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from registry.models import Note, Review
from registry.services import save_record

DATA_DIR = settings.REPO_DIR / "data"


class Command(BaseCommand):
    help = "Import notes.csv + results.json into the database"

    def add_arguments(self, parser):
        parser.add_argument("--notes", default=str(DATA_DIR / "notes.csv"))
        parser.add_argument("--results", default=str(DATA_DIR / "results.json"))
        parser.add_argument("--if-empty", action="store_true", help="skip if the database already has notes")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["if_empty"] and Note.objects.exists():
            self.stdout.write("Database already has notes; skipping import (--if-empty).")
            return
        csv.field_size_limit(sys.maxsize)  # long transcriptions exceed the default field limit
        try:
            with open(opts["notes"], newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            with open(opts["results"], encoding="utf-8") as f:
                results = json.load(f)
        except FileNotFoundError as e:
            raise CommandError(f"Missing file: {e.filename}") from e

        reviews = Review.objects.filter(extraction__note__source="mtsamples").count()
        Note.objects.filter(source="mtsamples").delete()
        if reviews:
            self.stdout.write(self.style.WARNING(f"Deleted {reviews} existing reviews of imported notes"))

        notes = {}
        for r in rows:
            notes[str(r["note_id"])] = Note.objects.create(
                external_id=str(r["note_id"]), source="mtsamples", sample_name=r["sample_name"],
                description=r.get("description", ""), transcription=r["transcription"],
                keywords=r.get("keywords", ""), answer_key=r.get("answer_key_procedures_approx", ""),
            )

        model_name, prompt_version = results.get("model", ""), results.get("prompt_version", "")
        imported, unknown = 0, []
        for rec in results["results"]:
            note = notes.get(str(rec["note_id"]))
            if note is None:
                unknown.append(rec["note_id"])
                continue
            save_record(note, rec, model_name, prompt_version)
            imported += 1

        failed = sum(1 for rec in results["results"] if rec["status"] != "ok")
        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(notes)} notes and {imported} extraction results "
            f"({failed} failed, kept for review); model={model_name}, prompt={prompt_version}"))
        missing = len(notes) - imported
        if missing:
            self.stdout.write(self.style.WARNING(f"{missing} notes have no result yet (status: pending)"))
        if unknown:
            self.stdout.write(self.style.WARNING(f"Skipped results for unknown note ids: {unknown}"))
