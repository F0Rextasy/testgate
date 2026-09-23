def test_truth():
    assert True


def test_empty():
    pass


def test_counts():
    result = compute()


@pytest.mark.skip("not ready")
def test_off():
    assert compute() == 1


def test_gated():
    if CI_ENABLED:
        assert compute() == 1
