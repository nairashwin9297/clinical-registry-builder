"""Phase 1: build data/notes.csv from the raw MTSamples dump.

Steps: filter to orthopedic operative notes, clean the text, derive
approximate procedure labels from sample_name + keywords, pick a
class-balanced sample of ~100 notes, and print a summary.

Run from the repo root:  python scripts/prepare_data.py
"""

import argparse
import csv
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW_CSV = REPO / "data" / "mtsamples.csv"
OUT_CSV = REPO / "data" / "notes.csv"

SPECIALTY = "Orthopedic"

# Procedure classes. Each class has two regex lists:
#   "name": matched against the cleaned sample_name (the most reliable signal)
#   "keywords": matched against individual keywords. Keywords also contain
#     diagnoses and anatomy, so these patterns are stricter, procedure-only phrases.
# A note can get several classes (e.g. "Anterior Cervical Discectomy & Fusion").
PROCEDURE_CLASSES = {
    "arthroplasty": {
        "name": [r"arthr?o?plast", r"replacement", r"hemi-?resurfacing"],
        "keywords": [r"arthroplasty", r"(joint|knee|hip|shoulder) replacement"],
    },
    "arthroscopy": {
        "name": [r"arthroscop", r"menisc", r"chondroplasty", r"labr", r"\bslap\b", r"bankart"],
        "keywords": [r"arthroscop"],
    },
    "fracture_fixation": {
        "name": [r"\borif\b", r"open reduction", r"closed reduction", r"intramedullary",
                 r"pinning", r"external fixation", r"osteosynthesis"],
        # "intramedullary guide" is a knee-replacement step, so require nail/rod.
        "keywords": [r"\borif\b", r"open reduction", r"closed reduction", r"intramedullary (nail|rod)",
                     r"percutaneous pinning", r"external fixat"],
    },
    "spinal_fusion": {
        # "arthrodesis" alone is also used for foot joints, so require a spine word.
        "name": [r"fusion", r"\btlif\b", r"(cervical|lumbar|spin\w*|thoracic).*arthrodesis"],
        "keywords": [r"\bfusion\b", r"interbody", r"\b(tlif|plif)\b",
                     r"(cervical|lumbar|spinal|vertebral|thoracic) arthrodesis"],
    },
    "spinal_decompression": {
        "name": [r"dis[ck]ectomy", r"lamin(ectomy|otomy)", r"foraminotomy", r"facetectomy",
                 r"transpedicular decompression", r"osteophytectomy"],
        "keywords": [r"dis[ck]ectomy", r"lamin(ectomy|otomy)", r"foraminotomy", r"facetectomy"],
    },
    "carpal_tunnel_release": {
        "name": [r"carpal tunnel", r"carpal ligament (release|reconstruction)"],
        "keywords": [r"carpal tunnel release", r"carpal ligament release"],
    },
    "soft_tissue_release": {
        # Tendon-sheath / compartment releases other than carpal tunnel.
        "name": [r"trigger (finger|thumb)", r"quervain", r"a1 pulley", r"compartment release",
                 r"hamstring release"],
        "keywords": [r"trigger (finger|thumb) release", r"a1 pulley release", r"quervain'?s? release",
                     r"compartment release", r"hamstring release"],
    },
    "tendon_ligament_repair": {
        # (?<!carpal ) so "Carpal Ligament Reconstruction" (a carpal tunnel case) isn't counted here.
        "name": [r"tendon.*repair", r"repair.*tendon", r"cuff repair",
                 r"(?<!carpal )ligament reconstruction", r"cruciate", r"palmaris longus repair"],
        "keywords": [r"rotator cuff repair", r"tendon repair", r"(?<!carpal )ligament reconstruction",
                     r"(acl|cruciate ligament) reconstruction"],
    },
    "bunionectomy_osteotomy": {
        "name": [r"bunion", r"osteotomy"],
        # Plain "osteotomy" appears as a step in hip/knee replacements, so name the type.
        "keywords": [r"bunionectomy",
                     r"(metatarsal|akin|austin|chevron|scarf|youngswick|calcaneal|wedge) osteotomy"],
    },
}

# Notes whose sample_name matches these are not operative notes or are
# non-surgical / out-of-scope procedures, even if they contain a PROCEDURE heading.
EXCLUDE_NAME = re.compile(
    r"discharge summary|consult|history and physical|\bh&p\b|letter|follow.?up|office"
    r"|lumbar puncture|discogram|\bblock\b|rhizotomy|radiofrequency|manipulation"
    r"|shockwave|ossatron|\bcast\b|aspiration|halo|kyphoplasty|vertebroplasty|mandib",
    re.IGNORECASE,
)

# A heading is an all-caps phrase ending in a colon, e.g. "PREOPERATIVE DIAGNOSIS:".
HEADING = r"[A-Z][A-Z0-9 /&()'#-]*[A-Z)]:"
# After cleaning, headings start a line; an operative note has one naming the procedure.
OPERATIVE_HEADING = re.compile(r"^[A-Z /&()'-]*\b(PROCEDURES?|OPERATIONS?)\b[A-Z /&()'-]*:", re.MULTILINE)


def clean_sample_name(name):
    """'Carpal Tunnel Release - 3 ' -> 'Carpal Tunnel Release'."""
    return re.sub(r"\s+-\s+\d+\s*$", "", name.strip())


def clean_transcription(text):
    """Undo MTSamples' comma-joined formatting.

    Raw notes look like 'foot.,PREOPERATIVE DIAGNOSIS: , Hallux...' because the
    original line breaks became commas. Put each heading on its own line.
    """
    t = text.strip()
    t = re.sub(rf"^({HEADING})\s*,?\s*", r"\1 ", t)        # heading at the very start
    t = re.sub(rf",\s*({HEADING})\s*,?\s*", r"\n\1 ", t)   # ",HEADING:," mid-text
    t = re.sub(r",\s*(\d{1,2}\.)\s+", r"\n\1 ", t)         # ",2.  Next item" lists
    t = re.sub(r"\.,\s*(?=[A-Z])", ".\n", t)                # "sentence.,Next paragraph"
    t = re.sub(r"[ \t]{2,}", " ", t)
    return "\n".join(line.strip() for line in t.split("\n")).strip()


def clean_keywords(raw):
    """Split keywords and drop the first one, which is the specialty name."""
    kws = [k.strip().lower() for k in raw.split(",") if k.strip()]
    if kws and kws[0] == SPECIALTY.lower():
        kws = kws[1:]
    return kws


def is_operative(clean_text):
    return bool(OPERATIVE_HEADING.search(clean_text))


def label_procedures(sample_name, keywords):
    """Approximate answer-key labels for one note (a sorted list of class names)."""
    name = sample_name.lower()
    labels = set()
    for cls, patterns in PROCEDURE_CLASSES.items():
        if any(re.search(p, name) for p in patterns["name"]):
            labels.add(cls)
        elif any(re.search(p, kw) for p in patterns["keywords"] for kw in keywords):
            labels.add(cls)
    # Carpal tunnel release is its own class; never also count it as "other soft-tissue release".
    if "carpal_tunnel_release" in labels:
        labels.discard("soft_tissue_release")
    return sorted(labels)


def select_balanced(notes, target, seed):
    """Round-robin over classes (rarest first) so big classes don't dominate.

    Each pass adds one more note for every class that still has candidates,
    until `target` notes are chosen. Seeded shuffle keeps it reproducible.
    """
    pool = sorted(notes, key=lambda n: n["note_id"])
    random.Random(seed).shuffle(pool)
    class_sizes = Counter(c for n in pool for c in n["labels"])
    order = sorted(class_sizes, key=lambda c: (class_sizes[c], c))

    selected, chosen_ids = [], set()
    while len(selected) < target:
        added = False
        for cls in order:
            if len(selected) >= target:
                break
            pick = next((n for n in pool if n["note_id"] not in chosen_ids and cls in n["labels"]), None)
            if pick:
                selected.append(pick)
                chosen_ids.add(pick["note_id"])
                added = True
        if not added:
            break
    return sorted(selected, key=lambda n: n["note_id"])


def load_raw(path):
    csv.field_size_limit(sys.maxsize)  # some transcriptions exceed the default field limit
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build(rows, target, seed):
    """Run the filter/label/select pipeline. Returns (selected notes, step counts, excluded names)."""
    steps = Counter(total=len(rows))
    ortho = [r for r in rows if r["medical_specialty"].strip() == SPECIALTY and r["transcription"].strip()]
    steps["orthopedic_nonempty"] = len(ortho)

    candidates, no_class = [], []
    for r in ortho:
        text = clean_transcription(r["transcription"])
        if not is_operative(text):
            continue
        steps["has_procedure_heading"] += 1
        name = clean_sample_name(r["sample_name"])
        if EXCLUDE_NAME.search(name):
            continue
        steps["after_name_exclusions"] += 1
        keywords = clean_keywords(r["keywords"])
        labels = label_procedures(name, keywords)
        if not labels:
            no_class.append(name)
            continue
        candidates.append({
            "note_id": int(r[""]),  # original MTSamples row index, for traceability
            "sample_name": name,
            "description": r["description"].strip(),
            "transcription": text,
            "keywords": keywords,
            "labels": labels,
        })
    steps["eligible_with_class"] = len(candidates)
    selected = select_balanced(candidates, target, seed)
    steps["selected"] = len(selected)
    return selected, candidates, steps, no_class


def write_notes(notes, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["note_id", "sample_name", "description", "transcription", "keywords",
                    "answer_key_procedures_approx"])
        for n in notes:
            w.writerow([n["note_id"], n["sample_name"], n["description"], n["transcription"],
                        ", ".join(n["keywords"]), "|".join(n["labels"])])


def print_summary(selected, candidates, steps, no_class):
    print("Filter steps:")
    for k in ["total", "orthopedic_nonempty", "has_procedure_heading", "after_name_exclusions",
              "eligible_with_class", "selected"]:
        print(f"  {k:24s} {steps[k]:5d}")
    print(f"\nExcluded (fit no procedure class): {len(no_class)}")
    print("  " + "; ".join(sorted(set(no_class))))

    eligible = Counter(c for n in candidates for c in n["labels"])
    chosen = Counter(c for n in selected for c in n["labels"])
    print("\nNotes per class (approximate answer key; a note can have several classes):")
    print(f"  {'class':24s} {'eligible':>8s} {'selected':>8s}")
    for cls in PROCEDURE_CLASSES:
        print(f"  {cls:24s} {eligible[cls]:8d} {chosen[cls]:8d}")
    multi = sum(1 for n in selected if len(n["labels"]) > 1)
    print(f"\nSelected notes with more than one class: {multi}")
    lengths = [len(n["transcription"]) for n in selected]
    if lengths:
        print(f"Transcription length (chars): min {min(lengths)}, "
              f"median {int(statistics.median(lengths))}, max {max(lengths)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=int, default=100, help="number of notes to select")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not RAW_CSV.exists():
        sys.exit(f"Missing {RAW_CSV}. Download MTSamples from Kaggle and place mtsamples.csv in data/.")
    selected, candidates, steps, no_class = build(load_raw(RAW_CSV), args.target, args.seed)
    write_notes(selected, OUT_CSV)
    print_summary(selected, candidates, steps, no_class)
    print(f"\nWrote {len(selected)} notes to {OUT_CSV.relative_to(REPO)}")


if __name__ == "__main__":
    main()
