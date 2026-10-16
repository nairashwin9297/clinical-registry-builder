"""CSV exports: a plain registry spreadsheet and a REDCap-style import file + data dictionary."""

import csv
import io

from . import extraction_core as core
from .services import final_values, note_status

REGISTRY_COLUMNS = ["note_id", "sample_name", "procedures", "body_part", "laterality", "patient_age",
                    "status", "answer_key_procedures_approx"]

# REDCap codes: choices are numbered, checkbox columns are named "<field>___<code>".
PROCEDURE_CODES = {cid: i for i, cid in enumerate(core.CLASS_IDS, start=1)}
LATERALITY_CODES = {"left": 1, "right": 2, "bilateral": 3, "not mentioned": 9}


def _csv(rows, header):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def registry_csv(notes):
    """One row per note with final values (human corrections applied)."""
    rows = []
    for n in notes:
        v = final_values(n)
        rows.append([n.external_id, n.sample_name, "|".join(v["procedure"]), v["body_part"], v["laterality"],
                     v["patient_age"], note_status(n), n.answer_key])
    return _csv(rows, REGISTRY_COLUMNS)


def redcap_csv(notes):
    """REDCap 'import records' layout matching redcap_dictionary_csv()."""
    header = (["record_id", "sample_name"] + [f"procedure___{c}" for c in PROCEDURE_CODES.values()]
              + ["body_part", "laterality", "patient_age", "registry_complete"])
    rows = []
    for n in notes:
        v = final_values(n)
        age = v["patient_age"]
        rows.append(
            [n.external_id, n.sample_name]
            + [1 if cid in v["procedure"] else 0 for cid in PROCEDURE_CODES]
            + [v["body_part"], LATERALITY_CODES.get(v["laterality"], ""), age if str(age).isdigit() else "",
               # REDCap form status: 2 = Complete (nothing left to review), 1 = Unverified.
               2 if note_status(n) == "ok" else 1]
        )
    return _csv(rows, header)


def redcap_dictionary_csv():
    """REDCap data dictionary describing the fields in redcap_csv()."""
    header = ["Variable / Field Name", "Form Name", "Section Header", "Field Type", "Field Label",
              "Choices, Calculations, OR Slider Labels", "Field Note", "Text Validation Type OR Show Slider Number",
              "Text Validation Min", "Text Validation Max", "Identifier?", "Branching Logic (Show field only if...)",
              "Required Field?", "Custom Alignment", "Question Number (surveys only)", "Matrix Group Name",
              "Matrix Ranking?", "Field Annotation"]
    blank = [""] * 13

    def field(name, ftype, label, choices="", validation="", vmin="", vmax=""):
        return [name, "registry", "", ftype, label, choices, "", validation, vmin, vmax] + blank[:8]

    proc_choices = " | ".join(f"{code}, {cid}" for cid, code in PROCEDURE_CODES.items())
    lat_choices = " | ".join(f"{code}, {name}" for name, code in LATERALITY_CODES.items())
    rows = [
        field("record_id", "text", "Note ID (MTSamples row index)"),
        field("sample_name", "text", "Sample name"),
        field("procedure", "checkbox", "Procedure classes", proc_choices),
        field("body_part", "text", "Body part"),
        field("laterality", "radio", "Laterality", lat_choices),
        field("patient_age", "text", "Patient age (years)", validation="integer", vmin="0", vmax="120"),
    ]
    return _csv(rows, header)
