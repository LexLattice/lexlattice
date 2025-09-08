# ruff: noqa: F821, F841
def f():
    try:
        g()
    except ValueError as e:
        raise RuntimeError('bad') from e
