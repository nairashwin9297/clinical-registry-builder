import pytest

from registry.metrics import compute_metrics, procedure_scores
from registry.models import Review
from registry.services import notes_with_extractions

from .conftest import failed_record, ok_record


def by_class(scores):
    return {r["class_id"]: r for r in scores["per_class"]}


def test_procedure_scores_per_class_and_overall():
    pairs = [
        ({"arthroscopy"}, {"arthroscopy"}),                        # exact
        ({"arthroscopy", "tendon_ligament_repair"}, {"arthroscopy"}),  # miss tendon (FN)
        ({"spinal_fusion"}, {"spinal_fusion", "spinal_decompression"}),  # extra decompression (FP)
        ({"carpal_tunnel_release"}, set()),                        # failed note: FN
    ]
    s = procedure_scores(pairs)
    c = by_class(s)
    assert (c["arthroscopy"]["tp"], c["arthroscopy"]["fp"], c["arthroscopy"]["fn"]) == (2, 0, 0)
    assert c["arthroscopy"]["precision"] == 1.0 and c["arthroscopy"]["recall"] == 1.0
    assert c["tendon_ligament_repair"]["recall"] == 0.0 and c["tendon_ligament_repair"]["precision"] is None
    assert c["spinal_decompression"]["precision"] == 0.0 and c["spinal_decompression"]["recall"] is None
    assert c["arthroplasty"]["f1"] is None  # never predicted, never in the key

    o = s["overall"]
    assert (o["tp"], o["fp"], o["fn"]) == (3, 1, 2)
    assert o["micro_precision"] == pytest.approx(3 / 4)
    assert o["micro_recall"] == pytest.approx(3 / 5)
    assert o["micro_f1"] == pytest.approx(2 * 0.75 * 0.6 / 1.35)
    assert o["exact_match"] == 1 and o["exact_match_rate"] == 0.25
    # Macro F1 averages classes present in the key: arthroscopy 1.0, tendon 0, fusion 1.0, carpal tunnel 0.
    assert c["tendon_ligament_repair"]["f1"] == 0.0 and c["carpal_tunnel_release"]["f1"] == 0.0
    assert o["macro_f1"] == pytest.approx(0.5)


def test_compute_metrics_from_db(make_note):
    make_note("1", "carpal_tunnel_release", record=ok_record("1"))
    make_note("2", "arthroscopy", record=failed_record("2"))
    make_note("3", "arthroscopy")  # pending: not counted as processed
    m = compute_metrics(notes_with_extractions())
    assert m["notes_total"] == 3 and m["notes_processed"] == 2 and m["notes_failed"] == 1
    assert m["fields_total"] == 8 and m["fields_flagged"] == 4 and m["flag_rate"] == 0.5
    assert m["notes_flagged"] == 1
    o = m["procedures"]["overall"]
    assert (o["tp"], o["fp"], o["fn"]) == (1, 0, 1)
    counts = {r["class_id"]: r for r in m["procedure_counts"]}
    assert counts["arthroscopy"] == {"class_id": "arthroscopy", "model": 0, "answer_key": 1}


def test_metrics_score_model_answers_not_reviews(make_note):
    note = make_note("1", "arthroscopy", record=ok_record("1"))  # model said carpal tunnel: wrong
    e = note.extractions.get(field="procedure")
    Review.objects.create(extraction=e, corrected_value="arthroscopy")
    m = compute_metrics(notes_with_extractions())
    assert m["procedures"]["overall"]["tp"] == 0  # the correction doesn't make the model look better
