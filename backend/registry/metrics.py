"""Metrics computed from stored extractions. Nothing here is hardcoded: every number comes from the DB.

Procedure accuracy compares the MODEL's answers (before human review) with the approximate answer key
from Phase 1, so it measures the model, not the reviewers.
"""

from collections import Counter

from . import extraction_core as core


def _ratio(num, den):
    return num / den if den else None  # None = undefined (e.g. precision of a class never predicted)


def _f1(tp, fp, fn):
    # F1 = 2TP / (2TP + FP + FN): equals the harmonic mean of precision and recall, and is 0 (not
    # undefined) for a class that is in the answer key but never predicted.
    return _ratio(2 * tp, 2 * tp + fp + fn)


def procedure_scores(pairs):
    """Per-class and overall precision/recall/F1.

    pairs: list of (answer_key_set, predicted_set) per note. A failed extraction predicts the empty set,
    so its answer-key classes count as misses (false negatives).
    """
    tp, fp, fn = Counter(), Counter(), Counter()
    exact = 0
    for gold, pred in pairs:
        for c in pred & gold:
            tp[c] += 1
        for c in pred - gold:
            fp[c] += 1
        for c in gold - pred:
            fn[c] += 1
        exact += gold == pred

    per_class = []
    for c in core.CLASS_IDS:
        p, r = _ratio(tp[c], tp[c] + fp[c]), _ratio(tp[c], tp[c] + fn[c])
        per_class.append({"class_id": c, "tp": tp[c], "fp": fp[c], "fn": fn[c],
                          "support": tp[c] + fn[c], "predicted": tp[c] + fp[c],
                          "precision": p, "recall": r, "f1": _f1(tp[c], fp[c], fn[c])})

    TP, FP, FN = sum(tp.values()), sum(fp.values()), sum(fn.values())
    micro_p, micro_r = _ratio(TP, TP + FP), _ratio(TP, TP + FN)
    macro = [row["f1"] for row in per_class if row["support"]]  # classes present in the answer key
    return {
        "per_class": per_class,
        "overall": {
            "notes": len(pairs),
            # "Match rate": the predicted set of classes is exactly the answer-key set.
            "exact_match": exact, "exact_match_rate": _ratio(exact, len(pairs)),
            "micro_precision": micro_p, "micro_recall": micro_r, "micro_f1": _f1(TP, FP, FN),
            "macro_f1": sum(macro) / len(macro) if macro else None,
            "tp": TP, "fp": FP, "fn": FN,
        },
    }


def compute_metrics(notes):
    """notes: iterable of Note with prefetched extractions (+ reviews)."""
    notes = list(notes)
    processed = [n for n in notes if n.extraction_status != "pending"]
    rows = [e for n in processed for e in n.extractions.all()]
    flagged = [e for e in rows if e.flagged]
    reviewed = [e for e in flagged if hasattr(e, "review")]
    notes_flagged = [n for n in processed if any(e.flagged for e in n.extractions.all())]

    pairs = []
    for n in processed:
        if not n.answer_key_list:
            continue  # uploaded notes without an answer key can't be scored
        pred = {e.value for e in n.extractions.all() if e.field == "procedure" and e.value in core.PROCEDURE_OPTIONS}
        pairs.append((set(n.answer_key_list), pred))
    scores = procedure_scores(pairs)

    # Counts per class for the dashboard chart: model answers vs the approximate answer key.
    predicted_counts = Counter(g for _, pred in pairs for g in pred)
    key_counts = Counter(g for gold, _ in pairs for g in gold)

    return {
        "notes_total": len(notes),
        "notes_processed": len(processed),
        "notes_failed": sum(n.extraction_status == "failed" for n in processed),
        "notes_scored": len(pairs),
        "fields_total": len(rows),
        "fields_flagged": len(flagged),
        "flag_rate": _ratio(len(flagged), len(rows)),
        "notes_flagged": len(notes_flagged),
        "notes_flagged_rate": _ratio(len(notes_flagged), len(processed)),
        "flags_reviewed": len(reviewed),
        "flag_reasons": _reason_counts(flagged),
        "procedures": scores,
        "procedure_counts": [{"class_id": c, "model": predicted_counts[c], "answer_key": key_counts[c]}
                             for c in core.CLASS_IDS],
    }


def _reason_counts(flagged):
    """Group flag reasons into a few buckets (reasons include note-specific text, e.g. the quoted age)."""
    def bucket(reason):
        if reason.startswith("Extraction failed"):
            return "Extraction failed (whole note)"
        if reason.startswith("Answered 'not mentioned'"):
            return "'Not mentioned' but the note seems to contain it"
        if "not one of the allowed" in reason or "not an allowed" in reason or "not a whole number" in reason:
            return "Value outside allowed options"
        return reason
    counts = Counter(bucket(e.flag_reason) for e in flagged)
    return [{"reason": r, "count": c} for r, c in counts.most_common()]
