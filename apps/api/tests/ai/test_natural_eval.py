from app.ai.evals.natural import auroc, choose_operating_point, stratified_split


def _rows():
    rows = []
    for lang, n_ans, n_un in (("en", 4, 3), ("ml", 4, 4), ("manglish", 4, 3)):
        for i in range(n_ans):
            rows.append({"id": f"a-{lang}-{i}", "language": lang, "type": "answerable"})
        for i in range(n_un):
            rows.append({"id": f"u-{lang}-{i}", "language": lang, "type": "unanswerable"})
    return rows


def test_stratified_split_is_deterministic_disjoint_and_balanced():
    rows = _rows()
    dev1, test1 = stratified_split(rows, seed=1)
    dev2, test2 = stratified_split(list(reversed(rows)), seed=1)
    assert [r["id"] for r in dev1] == [r["id"] for r in dev2]
    assert not {r["id"] for r in dev1} & {r["id"] for r in test1}
    assert len(dev1) + len(test1) == len(rows)
    for lang in ("en", "ml", "manglish"):
        for typ in ("answerable", "unanswerable"):
            d = sum(1 for r in dev1 if r["language"] == lang and r["type"] == typ)
            t = sum(1 for r in test1 if r["language"] == lang and r["type"] == typ)
            assert abs(d - t) <= 1


def test_operating_point_separable_scores_sit_in_gap():
    point = choose_operating_point([0.90, 0.88, 0.92], [0.80, 0.82, 0.78])
    assert 0.82 < point["threshold"] < 0.88
    assert point["false_answer_rate"] == 0.0
    assert point["false_abstain_rate"] == 0.0


def test_operating_point_prefers_fewer_false_answers_when_overlapping():
    point = choose_operating_point([0.90, 0.84, 0.92, 0.86], [0.85, 0.80, 0.78, 0.79])
    assert point["false_answer_rate"] == 0.0


def test_auroc_basic():
    assert auroc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert auroc([0.5], [0.5]) == 0.5
