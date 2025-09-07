# ruff: noqa: F821, F841


def case1():
    try:
        g()
    except ValueError as e:
        raise RuntimeError("bad") from e


def case2():
    try:
        g()
    except ValueError as e:
        raise RuntimeError("bad") from e


def case3():
    try:
        g()
    except ValueError as e:
        raise


def case4():
    try:
        g()
    except ValueError:
        raise RuntimeError("bad")


def case5():
    try:
        g()
    except ValueError as e:
        def inner():
            raise RuntimeError("bad")
        inner()

