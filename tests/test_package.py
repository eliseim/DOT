from importlib.metadata import version

import dot


def test_package_version() -> None:
    assert dot.__version__ == version("dot") == "1.1.1"
