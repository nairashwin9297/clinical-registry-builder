"""The Colab notebook must contain an exact copy of registry/extraction_core.py."""

import json

from django.conf import settings


def test_notebook_embeds_current_extraction_core():
    nb = json.loads((settings.REPO_DIR / "notebooks" / "extract.ipynb").read_text())
    cells = [c for c in nb["cells"] if c["metadata"].get("tag") == "core"]
    assert len(cells) == 1, "notebook should have exactly one 'core' cell"
    module = (settings.BASE_DIR / "registry" / "extraction_core.py").read_text()
    assert "".join(cells[0]["source"]) == module, "notebook is stale: run python scripts/build_notebook.py"
