from app.ai.evals.ml_eval import _evaluate_in_memory, has_heading_copy


def test_has_heading_copy_detects_verbatim_heading_and_allows_paraphrase():
    title = "RBI Master Direction: Digital Payment Security Controls"
    heading = "2. Internet Banking Security > Two-Factor Authentication"
    assert has_heading_copy("What are the Digital Payment Security Controls?", title, heading) is True
    paraphrase = "How do banks verify my identity before approving an online transfer?"
    assert has_heading_copy(paraphrase, title, heading) is False


def test_evaluate_in_memory_computes_kn_and_wilson_ci():
    cases = [
        {"id": "1", "language": "en", "type": "answerable", "question": "q1", "gold_chunk_ids": ["c1"]},
        {"id": "2", "language": "ml", "type": "unanswerable", "question": "q2", "gold_chunk_ids": []},
        {"id": "3", "language": "manglish", "type": "refusal", "question": "q3", "gold_chunk_ids": []},
    ]
    chunks = [{"chunk_id": "c1", "title": "Doc 1"}]
    q_vecs = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]
    c_vecs = [[1.0, 0.0]]
    res = _evaluate_in_memory(cases, chunks, q_vecs, c_vecs, {"en": 0.83, "ml": 0.79, "manglish": 0.82}, soft_min=0.76)
    assert res["overall"]["recall_at_5"]["k"] == 1
    assert res["overall"]["recall_at_5"]["n"] == 1
    assert res["overall"]["false_answer"]["k"] == 0
    assert res["overall"]["unsafe_answer"]["k"] == 1
    assert res["by_language"]["ml"]["indicative"] is True
