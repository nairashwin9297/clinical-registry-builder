"""Export the data the static GitHub Pages demo needs (no server there, just JSON files).

    python manage.py export_static [--out DIR]

Writes config.json, notes.json (every note with its extractions and evidence spans), metrics.json, and the
three CSV exports. Run it on a fresh import (no reviews): the static demo keeps reviews in the visitor's
browser, so the exported baseline must be the model's answers only. The CSVs double as a parity check:
the frontend test rebuilds them in JavaScript and compares.
"""

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from registry import exports
from registry.metrics import compute_metrics
from registry.models import Review
from registry.services import notes_with_extractions
from registry.views import config_dict, note_detail_dict

DEFAULT_OUT = settings.REPO_DIR / "frontend" / "public" / "demo-data"


class Command(BaseCommand):
    help = "Export notes, extractions and metrics as static JSON for the GitHub Pages demo"

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **opts):
        if Review.objects.exists():
            raise CommandError("The database has reviews. Export from a fresh import "
                               "(python manage.py import_results) so the demo starts from the model's answers.")
        out = Path(opts["out"])
        out.mkdir(parents=True, exist_ok=True)

        notes = list(notes_with_extractions())
        notes_json = json.dumps([note_detail_dict(n) for n in notes], ensure_ascii=False, separators=(",", ":"))
        config = config_dict()
        # The static site is always the read-only demo, whatever DEMO_MODE is where this runs.
        config.update(demo_mode=True, live_model=None, static=True)  # static: frontend reads files, not /api
        # Reviews in localStorage are tied to this version, so a new export never applies stale corrections.
        config["data_version"] = hashlib.sha256(notes_json.encode()).hexdigest()[:12]

        files = {
            "config.json": json.dumps(config, ensure_ascii=False, indent=1),
            "notes.json": notes_json,
            "metrics.json": json.dumps(compute_metrics(notes), indent=1),
            "registry.csv": exports.registry_csv(notes),
            "redcap.csv": exports.redcap_csv(notes),
            "redcap-dictionary.csv": exports.redcap_dictionary_csv(),
        }
        for name, content in files.items():
            # newline="" keeps the CSVs' \r\n line endings exactly as Python's csv module wrote them.
            with open(out / name, "w", encoding="utf-8", newline="") as f:
                f.write(content)
        self.stdout.write(self.style.SUCCESS(f"Exported {len(notes)} notes to {out} (data version {config['data_version']})"))
