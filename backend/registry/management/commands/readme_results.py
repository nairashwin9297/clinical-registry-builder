"""Print (or write into README.md) the results section, computed from the database.

    python manage.py readme_results                    # print
    python manage.py readme_results --write ../README.md
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from registry import extraction_core as core
from registry.metrics import compute_metrics
from registry.models import Note
from registry.readme import replace_section, results_markdown
from registry.services import notes_with_extractions


class Command(BaseCommand):
    help = "Generate the README results section from the database"

    def add_arguments(self, parser):
        parser.add_argument("--write", metavar="README", help="replace the marked section in this file")

    def handle(self, *args, **opts):
        models = sorted(set(Note.objects.exclude(model_name="").values_list("model_name", flat=True)))
        body = results_markdown(compute_metrics(notes_with_extractions()), models, core.PROMPT_VERSION)
        if not opts["write"]:
            self.stdout.write(body)
            return
        path = Path(opts["write"])
        try:
            path.write_text(replace_section(path.read_text(encoding="utf-8"), body), encoding="utf-8")
        except ValueError as e:
            raise CommandError(f"{path}: {e}") from e
        self.stdout.write(self.style.SUCCESS(f"Updated results section in {path}"))
