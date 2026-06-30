from benchmark.model_keys import CASO1, CASO1_SHORT


def test_caso1_has_one_model_per_paradigm():
    assert len(CASO1) == 6
    paradigms = [k.split("/")[0] for k in CASO1]
    assert len(set(paradigms)) == 6, f"expected 6 distinct paradigms, got {paradigms}"
    assert all(k.count("/") == 1 for k in CASO1)


def test_caso1_short_labels_cover_every_key():
    assert set(CASO1_SHORT) == set(CASO1)
