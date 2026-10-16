"""Shared extraction logic: parsing, validation, retry loop, quote matching, flag rules."""

import hashlib
import json

import pytest

from registry import extraction_core as core

from .conftest import NOTE_TEXT


def reply(procedures=(("carpal_tunnel_release", "Right carpal tunnel release"),), body_ev="carpal tunnel",
          lat="right", lat_ev="right hand", age=45, age_ev="45-year-old woman", fence=False):
    obj = {"procedure": [{"value": v, "evidence": e} for v, e in procedures],
           "body_part": {"value": "Wrist", "evidence": body_ev},
           "laterality": {"value": lat, "evidence": lat_ev},
           "patient_age": {"value": age, "evidence": age_ev}}
    s = json.dumps(obj)
    return f"Here you go:\n```json\n{s}\n```" if fence else s


def scripted(*replies):
    """A fake generate() that returns the given replies in order (or raises an exception given as one)."""
    calls = []

    def generate(messages):
        calls.append(messages)
        r = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(r, Exception):
            raise r
        return r
    return generate, calls


# --- prompt -----------------------------------------------------------------------------------------

def test_prompt_change_requires_version_bump():
    # Colab results record PROMPT_VERSION. If you edit SYSTEM_PROMPT, bump PROMPT_VERSION and update this hash.
    digest = hashlib.sha256(core.SYSTEM_PROMPT.encode()).hexdigest()[:16]
    assert (core.PROMPT_VERSION, digest) == ("v3", PROMPT_HASH_V3)


PROMPT_HASH_V3 = "19d2d046b8289fb0"  # sha256 prefix of the v3 prompt used for data/results.json


def test_prompt_lists_every_class_id():
    for cid in core.CLASS_IDS:
        assert f'"{cid}"' in core.SYSTEM_PROMPT


# --- parsing / validation ---------------------------------------------------------------------------

def test_parse_json_strips_fences_and_preamble():
    assert core.parse_json(reply(fence=True))["body_part"]["value"] == "Wrist"


def test_parse_json_rejects_truncated_reply():
    with pytest.raises(ValueError, match="invalid JSON"):
        core.parse_json('{"procedure": [{"value": "arthroscopy", "evidence": "x"},')


def test_validate_normalizes_formatting_and_rejects_free_text():
    obj = json.loads(reply(procedures=[("Carpal Tunnel Release", "a"), ("carpal_tunnel_release", "dup"),
                                       ("ulnar nerve transposition", "b")], age="45"))
    fields, rejected, missing = core.validate(obj)
    assert fields["procedure"] == [{"value": "carpal_tunnel_release", "evidence": "a"}]  # duplicate dropped
    assert [r["value"] for r in rejected] == ["ulnar nerve transposition"]
    assert fields["body_part"]["value"] == "wrist" and fields["patient_age"]["value"] == 45
    assert missing == []


def test_validate_reports_missing_quotes_but_not_for_not_mentioned():
    obj = json.loads(reply(body_ev="", age="not mentioned", age_ev=""))
    _, _, missing = core.validate(obj)
    assert missing == ["body_part"]


@pytest.mark.parametrize("bad", [[], {"procedure": []}, {**json.loads(reply()), "procedure": "x"}])
def test_validate_rejects_bad_structure(bad):
    with pytest.raises(ValueError):
        core.validate(bad)


# --- retry loop -------------------------------------------------------------------------------------

def test_extract_note_ok_first_try():
    gen, calls = scripted(reply())
    rec = core.extract_note("n1", NOTE_TEXT, gen)
    assert rec["status"] == "ok" and rec["attempts"] == 1 and rec["error"] is None and len(calls) == 1


def test_extract_note_retries_once_after_invalid_json():
    gen, calls = scripted("not json", reply())
    rec = core.extract_note("n1", NOTE_TEXT, gen)
    assert rec["status"] == "ok" and rec["attempts"] == 2
    assert [m["role"] for m in calls[1]] == ["system", "user", "assistant", "user"]


def test_extract_note_records_failure_after_two_bad_replies():
    gen, _ = scripted("nope", '{"procedure": 5}')
    rec = core.extract_note("n1", NOTE_TEXT, gen)
    assert rec["status"] == "failed" and rec["attempts"] == 2 and len(rec["raw_outputs"]) == 2


def test_extract_note_keeps_partial_result_when_retry_still_has_invalid_class():
    bad = reply(procedures=[("carpal_tunnel_release", "x"), ("bursa excision", "y")])
    gen, calls = scripted(bad, bad)
    rec = core.extract_note("n1", NOTE_TEXT, gen)
    assert rec["status"] == "ok" and [r["value"] for r in rec["rejected_procedures"]] == ["bursa excision"]
    assert "Each value must be exactly one of" in calls[1][-1]["content"][0]["text"]


def test_extract_note_turns_generation_error_into_failed_record():
    gen, _ = scripted(ConnectionError("refused"))
    rec = core.extract_note("n1", NOTE_TEXT, gen)
    assert rec["status"] == "failed" and rec["error"].startswith("generation error")


# --- quote matching ---------------------------------------------------------------------------------

def test_locate_quote_exact_ignores_case_punctuation_and_returns_span():
    match, (s, e) = core.locate_quote("right CARPAL-tunnel release", NOTE_TEXT)
    assert match == "exact" and NOTE_TEXT[s:e] == "Right carpal tunnel release"


def test_locate_quote_whole_words_only():
    assert core.quote_match("ight carpal", NOTE_TEXT) is None


def test_locate_quote_near_verbatim_and_ellipsis():
    assert core.quote_match("The patient is a 45-year-old lady with numbness of the right hand", NOTE_TEXT) == "near"
    assert core.quote_match("Right carpal tunnel release ... ligament was divided", NOTE_TEXT) == "near"


def test_locate_quote_paraphrase_not_found():
    assert core.quote_match("the surgeon released the carpal tunnel", NOTE_TEXT) is None


# --- flag rules -------------------------------------------------------------------------------------

@pytest.mark.parametrize("field,value,quote,expected", [
    ("procedure", "carpal_tunnel_release", "Right carpal tunnel release", None),
    ("procedure", "carpal_tunnel_release", "", "No evidence quote given"),
    ("procedure", "carpal_tunnel_release", "left knee scope", "Evidence quote not found in the note"),
    ("procedure", "osteotomy", "x", "'osteotomy' is not one of the allowed procedure classes"),
    ("laterality", "anterior", "x", "'anterior' is not an allowed laterality option"),
    ("patient_age", "2-1/2-year-old", "x", "'2-1/2-year-old' is not a whole number or 'not mentioned'"),
    ("body_part", "not mentioned", "", "Answered 'not mentioned'"),
    ("patient_age", "not mentioned", "", "Answered 'not mentioned', but the note contains '45-year-old'"),
    ("laterality", "not mentioned", "", "Answered 'not mentioned', but the note contains 'Right'"),
])
def test_flag_reason(field, value, quote, expected):
    assert core.flag_reason(field, value, quote, NOTE_TEXT)[0] == expected


def test_not_mentioned_is_fine_when_note_lacks_the_information():
    text = "PROCEDURE: Trigger finger release of the digit."
    assert core.flag_reason("patient_age", "not mentioned", "", text) == (None, "")
    assert core.flag_reason("laterality", "not mentioned", "", text) == (None, "")


def test_build_extractions_for_failed_record_flags_every_field():
    rows = core.build_extractions({"status": "failed", "error": "invalid JSON: x"}, NOTE_TEXT)
    assert [r["field"] for r in rows] == core.FIELDS
    assert all(r["flagged"] and r["flag_reason"].startswith("Extraction failed") for r in rows)


def test_build_extractions_flags_empty_procedure_list():
    rec = json.loads(reply(procedures=[]))
    fields, _, _ = core.validate(rec)
    rows = core.build_extractions({"status": "ok", "fields": fields, "rejected_procedures": []}, NOTE_TEXT)
    proc = [r for r in rows if r["field"] == "procedure"]
    assert len(proc) == 1 and proc[0]["flag_reason"] == "No procedure class found"
