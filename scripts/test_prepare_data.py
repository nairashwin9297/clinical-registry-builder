from prepare_data import (
    clean_keywords,
    clean_sample_name,
    clean_transcription,
    is_operative,
    label_procedures,
    select_balanced,
)


def test_clean_sample_name_strips_numeric_suffix():
    assert clean_sample_name("Carpal Tunnel Release - 3 ") == "Carpal Tunnel Release"
    assert clean_sample_name(" ORIF - Left Tibia ") == "ORIF - Left Tibia"  # non-numeric suffix kept


def test_clean_transcription_puts_headings_on_own_lines():
    raw = ("TITLE OF OPERATION: , Youngswick osteotomy.,PREOPERATIVE DIAGNOSIS: , Hallux limitus."
           ",ANESTHESIA:,  Monitored care.,PROCEDURE:,1.  First step.,2.  Second step.")
    assert clean_transcription(raw) == (
        "TITLE OF OPERATION: Youngswick osteotomy.\n"
        "PREOPERATIVE DIAGNOSIS: Hallux limitus.\n"
        "ANESTHESIA: Monitored care.\n"
        "PROCEDURE: 1. First step.\n"
        "2. Second step."
    )


def test_clean_transcription_splits_paragraphs_but_keeps_inline_commas():
    raw = "PROCEDURE: , Left knee, medial side.,The patient tolerated it."
    assert clean_transcription(raw) == "PROCEDURE: Left knee, medial side.\nThe patient tolerated it."


def test_clean_keywords_drops_specialty():
    assert clean_keywords("orthopedic, Carpal Tunnel Release, , tourniquet") == ["carpal tunnel release", "tourniquet"]
    assert clean_keywords("") == []


def test_is_operative_needs_procedure_or_operation_heading():
    assert is_operative("PREOPERATIVE DIAGNOSIS: x\nPROCEDURE PERFORMED: y")
    assert is_operative("TITLE OF OPERATION: y")
    assert not is_operative("CHIEF COMPLAINT: knee pain\nPLAN: surgery next week")
    # "PREOPERATIVE" alone must not count as an OPERATION heading.
    assert not is_operative("PREOPERATIVE DIAGNOSIS: x")


def test_label_multi_class_from_name():
    assert label_procedures("Anterior Cervical Discectomy & Fusion", []) == [
        "spinal_decompression", "spinal_fusion"]


def test_label_uses_keywords_as_backup():
    assert label_procedures("Anterior Cervical Discectomy", ["cervical fusion"]) == [
        "spinal_decompression", "spinal_fusion"]


def test_label_ignores_diagnosis_keywords():
    # "carpal tunnel syndrome" is a diagnosis, not a procedure.
    assert label_procedures("Ulnar Nerve Transposition", ["carpal tunnel syndrome"]) == []
    # "intramedullary guide" is a step of knee replacement, not fracture fixation.
    assert label_procedures("Knee Arthroplasty - Revision", ["intramedullary guide"]) == ["arthroplasty"]


def test_foot_arthrodesis_is_not_spinal_fusion():
    assert "spinal_fusion" not in label_procedures("Bunionectomy & Arthrodesis", [])


def test_carpal_tunnel_and_soft_tissue_release_are_exclusive():
    labels = label_procedures("Endoscopic Carpal Tunnel & de Quervain's Release", [])
    assert labels == ["carpal_tunnel_release"]
    assert label_procedures("de Quervain Release - Carpal", []) == ["soft_tissue_release"]
    assert label_procedures("Carpal Ligament Reconstruction", []) == ["carpal_tunnel_release"]


def test_unlabelled_note_gets_no_class():
    assert label_procedures("Ganglion Excision", ["excision"]) == []


def _notes():
    notes = [{"note_id": i, "labels": ["big"]} for i in range(50)]
    notes += [{"note_id": 100 + i, "labels": ["small"]} for i in range(5)]
    return notes


def test_select_balanced_takes_rare_classes_and_is_reproducible():
    picked = select_balanced(_notes(), target=10, seed=1)
    assert len(picked) == 10
    assert sum(1 for n in picked if "small" in n["labels"]) == 5
    assert picked == select_balanced(_notes(), target=10, seed=1)


def test_select_balanced_stops_when_pool_exhausted():
    assert len(select_balanced(_notes(), target=500, seed=1)) == 55
