def test_sum():
    assert compute() + 1 == 2


def test_raises():
    with raises(ValueError):
        parse("x")
