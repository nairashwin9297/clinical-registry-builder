# Shared extraction logic: prompt, JSON parsing/validation, the retry loop, quote matching and flag rules.
#
# This file is the single source of truth. It is used by the Django backend (import + live Ollama mode)
# AND copied verbatim into notebooks/extract.ipynb by scripts/build_notebook.py, so Colab and live mode
# behave the same. Plain Python only: no Django, no torch. After editing, run scripts/build_notebook.py
# (a test fails if the notebook copy drifts).

import difflib
import json
import re
import time

PROMPT_VERSION = "v3"   # bump whenever SYSTEM_PROMPT changes; results record which prompt made them
MAX_NEW_TOKENS = 768    # enough for the JSON reply; long notes have several procedures + quotes

# Class IDs must match PROCEDURE_CLASSES in scripts/prepare_data.py.
PROCEDURE_OPTIONS = {
    "arthroplasty": "joint replacement or resurfacing, total or partial (hemiarthroplasty), any joint, "
                    "including resection or interposition arthroplasty",
    "arthroscopy": "any arthroscopic (scope) procedure, e.g. meniscectomy, chondroplasty, arthroscopic labral repair",
    "fracture_fixation": "fixing a fracture: ORIF, closed reduction, pinning, intramedullary nail/rod, external fixation. "
                         "Screw fixation of a planned osteotomy (e.g. in a bunion operation) is NOT fracture_fixation",
    "spinal_fusion": "spinal fusion or arthrodesis of vertebrae, including interbody fusion and TLIF",
    "spinal_decompression": "discectomy, laminectomy, laminotomy, foraminotomy or facetectomy of the spine",
    "carpal_tunnel_release": "cutting the transverse carpal ligament at the wrist (open or endoscopic)",
    "soft_tissue_release": "trigger finger/thumb (A1 pulley) release, de Quervain (first dorsal compartment) "
                           "release, or hamstring release; never carpal tunnel",
    "tendon_ligament_repair": "repair or reconstruction of a tendon or ligament, e.g. rotator cuff repair, "
                              "ACL reconstruction, Achilles tendon repair",
    "bunionectomy_osteotomy": "bunionectomy, or an osteotomy of a foot bone (e.g. Austin, Akin, metatarsal osteotomy)",
}
CLASS_IDS = list(PROCEDURE_OPTIONS)
FIELDS = ["procedure", "body_part", "laterality", "patient_age"]
LATERALITY_OPTIONS = ["left", "right", "bilateral", "not mentioned"]
NOT_MENTIONED = "not mentioned"

class_lines = "\n".join(f"  {cid}: {desc}" for cid, desc in PROCEDURE_OPTIONS.items())
id_list = ", ".join(f'"{cid}"' for cid in CLASS_IDS)

SYSTEM_PROMPT = f"""You extract structured data from orthopedic operative notes for a research registry.
Reply with ONLY one JSON object, no markdown fences and no text before or after it.

FIELD 1, procedure: a list of procedure class IDs. Allowed IDs (ID: meaning):
{class_lines}
Rules for procedure:
- Each "value" MUST be one of these exact IDs, copied character for character: {id_list}.
  Never write a procedure name, abbreviation or any other text as the value.
- Include an ID only if the note says that procedure was performed in THIS operation
  (not a diagnosis, a past surgery or a plan). Do not guess from the body part alone.
- Procedures that match no ID (e.g. nerve transposition, bursa excision, hardware removal) are left out.
- A note can have several IDs. If none apply, use an empty list [].

FIELD 2, body_part: the main body part operated on, short and lowercase, without the side
  (e.g. "knee", "hip", "shoulder", "wrist", "hand", "finger", "thumb", "foot", "ankle", "cervical spine", "lumbar spine").
FIELD 3, laterality: exactly one of "left", "right", "bilateral", "not mentioned".
FIELD 4, patient_age: the patient's age in years as an integer, or "not mentioned".

EVIDENCE RULES (apply to every field, including body_part and laterality):
- Every value that is not "not mentioned" MUST have a non-empty "evidence" quote.
- The quote is a short phrase of about 3 to 15 words, copied EXACTLY from the note as one continuous
  piece of text: same words, same order. Do not reword, summarize, fix spelling, join separate
  sentences, or use "...".
- Only when a value is "not mentioned" is its evidence "".

JSON format:
{{
  "procedure": [{{"value": "<one of the allowed IDs>", "evidence": "<exact quote>"}}],
  "body_part": {{"value": "<body part>", "evidence": "<exact quote>"}},
  "laterality": {{"value": "<left|right|bilateral|not mentioned>", "evidence": "<exact quote>"}},
  "patient_age": {{"value": <integer or "not mentioned">, "evidence": "<exact quote>"}}
}}

Worked example. Note:
PROCEDURE: Left knee arthroscopy with partial medial meniscectomy.
HISTORY: The patient is a 54-year-old man with a medial meniscus tear of the left knee.
Correct reply:
{{
  "procedure": [{{"value": "arthroscopy", "evidence": "Left knee arthroscopy with partial medial meniscectomy"}}],
  "body_part": {{"value": "knee", "evidence": "Left knee arthroscopy"}},
  "laterality": {{"value": "left", "evidence": "medial meniscus tear of the left knee"}},
  "patient_age": {{"value": 54, "evidence": "The patient is a 54-year-old man"}}
}}
If that note had no age, patient_age would be {{"value": "not mentioned", "evidence": ""}}."""


# ---------------------------------------------------------------------------------------------------
# Prompt + reply validation
# ---------------------------------------------------------------------------------------------------

def text_msg(role, text):
    # Gemma 3's processor expects content as a list of typed parts.
    return {"role": role, "content": [{"type": "text", "text": text}]}


def build_messages(note_text):
    return [text_msg("system", SYSTEM_PROMPT),
            text_msg("user", f"Operative note:\n\n{note_text}")]


def parse_json(reply):
    """Pull the JSON object out of the reply. Small models often add ```json fences or a preamble."""
    text = re.sub(r"```(?:json)?", "", reply).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the reply")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e


def check_value_evidence(field, item):
    if not isinstance(item, dict) or "value" not in item or "evidence" not in item:
        raise ValueError(f'{field} must be an object with "value" and "evidence"')
    if not isinstance(item["evidence"], str):
        raise ValueError(f"{field}.evidence must be a string")


def to_class_id(value):
    """Fix formatting only: 'Carpal Tunnel Release' / 'carpal-tunnel release' -> 'carpal_tunnel_release'.
    Returns None if the result still isn't an allowed ID."""
    cid = re.sub(r"[\s\-/]+", "_", value.strip().strip("\"'").lower())
    return cid if cid in PROCEDURE_OPTIONS else None


def validate(obj):
    """Check structure and procedure IDs.

    Raises ValueError for unusable structure. Otherwise returns (fields, rejected, missing_quotes):
    `rejected` holds procedure items whose value isn't an allowed class ID, `missing_quotes` names
    fields that have a value but an empty quote.
    """
    if not isinstance(obj, dict):
        raise ValueError("reply must be a JSON object")
    missing = [f for f in FIELDS if f not in obj]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    if not isinstance(obj["procedure"], list):
        raise ValueError("procedure must be a list")
    for field in ["body_part", "laterality", "patient_age"]:
        check_value_evidence(field, obj[field])
    for field in ["body_part", "laterality"]:
        if not isinstance(obj[field]["value"], str):
            raise ValueError(f"{field}.value must be a string")
    age = obj["patient_age"]["value"]
    if isinstance(age, bool) or not isinstance(age, (int, str)):
        raise ValueError('patient_age.value must be an integer or "not mentioned"')

    procedures, rejected, seen = [], [], set()
    for item in obj["procedure"]:
        check_value_evidence("procedure item", item)
        cid = to_class_id(item["value"]) if isinstance(item["value"], str) else None
        if cid is None:
            rejected.append(item)
        elif cid not in seen:  # drop duplicates of the same class
            seen.add(cid)
            procedures.append({"value": cid, "evidence": item["evidence"]})

    # Light normalization only. Out-of-option laterality etc. is flagged later, not rejected here.
    if isinstance(age, str) and age.strip().isdigit():
        age = int(age.strip())
    elif isinstance(age, str):
        age = age.strip().lower()
    fields = {
        "procedure": procedures,
        "body_part": {"value": obj["body_part"]["value"].strip().lower(), "evidence": obj["body_part"]["evidence"]},
        "laterality": {"value": obj["laterality"]["value"].strip().lower(), "evidence": obj["laterality"]["evidence"]},
        "patient_age": {"value": age, "evidence": obj["patient_age"]["evidence"]},
    }
    return fields, rejected, missing_quotes(fields)


def missing_quotes(fields):
    """Names of fields that have a real value but an empty evidence quote."""
    missing = [f"procedure {p['value']}" for p in fields["procedure"] if not p["evidence"].strip()]
    for f in ["body_part", "laterality", "patient_age"]:
        v = fields[f]
        if str(v["value"]).strip().lower() != NOT_MENTIONED and not v["evidence"].strip():
            missing.append(f)
    return missing


def extract_note(note_id, note_text, generate):
    """Extract one note with `generate(messages) -> reply text` (Gemma in Colab, Ollama locally).

    Up to 2 attempts. Never raises: generation errors and unusable replies become a 'failed' record.
    """
    messages = build_messages(note_text)
    raw_outputs, error, partial = [], None, None
    started = time.time()

    def record(status, fields=None, rejected=()):
        return {"note_id": note_id, "status": status, "attempts": len(raw_outputs),
                "fields": fields, "rejected_procedures": list(rejected), "error": error,
                "raw_outputs": raw_outputs, "seconds": round(time.time() - started, 1)}

    for attempt in (1, 2):
        try:
            reply = generate(messages)
        except Exception as e:  # e.g. CUDA out of memory, or Ollama not reachable
            error = f"generation error: {type(e).__name__}: {e}"
            break
        raw_outputs.append(reply)
        try:
            fields, rejected, no_quote = validate(parse_json(reply))
        except ValueError as e:
            error = str(e)
            problem = f"That reply was not valid ({error})."
        else:
            if not rejected and not no_quote:
                error = None
                return record("ok", fields)
            partial = (fields, rejected)  # usable, apart from bad procedure values / missing quotes
            errors, problems = [], []
            if rejected:
                bad = ", ".join(repr(r["value"]) for r in rejected)
                errors.append(f"procedure values not in the allowed list: {bad}")
                problems.append(f"These procedure values are not allowed IDs: {bad}. Each value must be exactly "
                                f"one of: {id_list}. Leave out procedures that match no ID.")
            if no_quote:
                errors.append(f"empty evidence for: {', '.join(no_quote)}")
                problems.append(f"These fields have a value but an empty evidence quote: {', '.join(no_quote)}. "
                                "Every value that is not \"not mentioned\" needs a short exact quote from the note.")
            error = "; ".join(errors)
            problem = " ".join(problems)
        if attempt == 1:
            # Retry once: show the model its own reply and what was wrong with it.
            messages = messages + [
                text_msg("assistant", reply),
                text_msg("user", problem + " Reply again with ONLY the JSON object, nothing else."),
            ]

    if partial:
        # Still imperfect after the retry: keep the usable fields and record the invalid procedure values.
        # Missing quotes stay as "" and get flagged.
        return record("ok", *partial)
    return record("failed")


# ---------------------------------------------------------------------------------------------------
# Quote matching
# ---------------------------------------------------------------------------------------------------

NEAR_MATCH = 0.9  # share of quote words that must line up with the note for a near-verbatim match
_WORD = re.compile(r"[a-z0-9]+")


def normalize_for_match(text):
    """Lowercase and turn every run of punctuation/whitespace into one space.

    So 'Right carpal tunnel release.' matches 'right  carpal-tunnel release', and the model dropping
    a period or changing a comma doesn't count as a misquote.
    """
    return " ".join(_WORD.findall(str(text).lower()))


def _words(text):
    """Words of the normalized text, with their character offsets in the original text."""
    return [(m.group(), m.start(), m.end()) for m in _WORD.finditer(str(text).lower())]


def _find_run(needle, haystack):
    """Index where the word list `needle` appears contiguously in `haystack`, or None."""
    k = len(needle)
    for i in range(len(haystack) - k + 1):
        if haystack[i:i + k] == needle:
            return i
    return None


def locate_quote(quote, note_text):
    """Find the quote in the note. Returns (match_type, (start, end)) or (None, None).

    match_type is "exact" (same words in order, ignoring case/punctuation) or "near" (near-verbatim).
    (start, end) are character offsets in note_text, used to highlight the evidence in the UI.
    Matching is on whole words, so "right" never matches inside "bright".
    """
    note = _words(note_text)
    note_words = [w for w, _, _ in note]
    q = [w for w, _, _ in _words(quote)]
    if not q:
        return None, None

    def span(i, k):
        return note[i][1], note[i + k - 1][2]

    i = _find_run(q, note_words)
    if i is not None:
        return "exact", span(i, len(q))

    # A quote stitched together with "..." counts if every piece is in the note.
    pieces = [[w for w, _, _ in _words(p)] for p in re.split(r"\.\.\.|…", str(quote))]
    pieces = [p for p in pieces if p]
    if len(pieces) > 1:
        found = [(_find_run(p, note_words), len(p)) for p in pieces]
        if all(i is not None for i, _ in found):
            spans = [span(i, k) for i, k in found]
            return "near", (min(s for s, _ in spans), max(e for _, e in spans))

    # Otherwise slide a window the length of the quote over the note and compare word sequences,
    # so one changed or dropped word in a 10+ word quote still counts. Short quotes must be exact.
    if len(q) >= 5:
        sm = difflib.SequenceMatcher(autojunk=False)
        sm.set_seq2(q)
        for i in range(max(1, len(note_words) - len(q) + 1)):
            sm.set_seq1(note_words[i:i + len(q)])
            if sm.quick_ratio() >= NEAR_MATCH and sm.ratio() >= NEAR_MATCH:
                return "near", span(i, min(len(q), len(note_words) - i))
    return None, None


def quote_match(quote, note_text):
    """How the quote appears in the note: "exact", "near", or None (not found)."""
    return locate_quote(quote, note_text)[0]


# ---------------------------------------------------------------------------------------------------
# Flag rules (decide which answers a human should review)
# ---------------------------------------------------------------------------------------------------

# "Not mentioned" is only doubtful if the note seems to contain the information.
AGE_PATTERN = re.compile(r"\b\d{1,3}\s*-?\s*(?:year|yr)s?\s*-?\s*old\b|\bage[d:]?\s+\d{1,3}\b", re.IGNORECASE)
LATERALITY_PATTERN = re.compile(r"\b(?:left|right|bilateral(?:ly)?)\b", re.IGNORECASE)


def flag_reason(field, value, quote, note_text):
    """Return (reason, match_type). reason is None when the answer looks trustworthy.

    Rules, in order: value outside the allowed options; "not mentioned" when the note seems to
    contain the answer; no evidence quote; evidence quote not found in the note.
    """
    v = str(value).strip().lower()
    if field == "procedure" and v not in PROCEDURE_OPTIONS:
        return f"'{value}' is not one of the allowed procedure classes", ""
    if field == "laterality" and v not in LATERALITY_OPTIONS:
        return f"'{value}' is not an allowed laterality option", ""
    if field == "patient_age" and v != NOT_MENTIONED and not (isinstance(value, int) or v.isdigit()):
        return f"'{value}' is not a whole number or 'not mentioned'", ""

    if v == NOT_MENTIONED:
        if field == "patient_age":
            hit = AGE_PATTERN.search(note_text)
        elif field == "laterality":
            hit = LATERALITY_PATTERN.search(note_text)
        else:  # every operative note has a body part
            return "Answered 'not mentioned'", ""
        return (f"Answered 'not mentioned', but the note contains '{hit.group(0)}'", "") if hit else (None, "")

    if not str(quote).strip():
        return "No evidence quote given", ""
    match, _ = locate_quote(quote, note_text)
    if match is None:
        return "Evidence quote not found in the note", ""
    return None, match


def build_extractions(record, note_text):
    """Turn one extraction record into flat per-field rows with flags.

    One row per procedure class plus one each for body_part, laterality and patient_age. Each row:
    {field, value, evidence_quote, flagged, flag_reason, match_type}. Used by the backend import and
    live mode, and by the notebook's flag-rate preview, so both count flags the same way.
    """
    def row(field, value, quote="", reason=None, match=""):
        return {"field": field, "value": "" if value is None else str(value), "evidence_quote": quote,
                "flagged": reason is not None, "flag_reason": reason or "", "match_type": match}

    if record["status"] != "ok":
        # Whole-note failure (e.g. invalid JSON after the retry): every field goes to the review queue.
        reason = f"Extraction failed: {record.get('error') or 'unknown error'}"
        return [row(f, "", reason=reason) for f in FIELDS]

    fields = record["fields"]
    rows = []
    for p in fields["procedure"]:
        reason, match = flag_reason("procedure", p["value"], p["evidence"], note_text)
        rows.append(row("procedure", p["value"], p["evidence"], reason, match))
    for p in record.get("rejected_procedures", []):
        rows.append(row("procedure", p.get("value"), p.get("evidence", ""),
                        f"'{p.get('value')}' is not one of the allowed procedure classes"))
    if not rows:
        rows.append(row("procedure", "", reason="No procedure class found"))
    for f in ["body_part", "laterality", "patient_age"]:
        v = fields[f]
        reason, match = flag_reason(f, v["value"], v["evidence"], note_text)
        rows.append(row(f, v["value"], v["evidence"], reason, match))
    return rows
