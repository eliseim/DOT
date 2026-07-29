from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_explains_python_requirement_and_requests_package_approval() -> None:
    text = (ROOT / "launch_dot_gui.cmd").read_text(encoding="utf-8")

    assert "Python 3.11, 3.12, or 3.13" in text
    assert "Tcl/Tk" in text
    assert "Approve package installation? [Y/N]" in text
    assert "if errorlevel 2 goto setup_cancelled" in text
    assert text.index("call :approve_packages") < text.index('-m venv ".venv"')


def test_windows_launcher_lists_every_direct_runtime_package_before_approval() -> None:
    text = (ROOT / "launch_dot_gui.cmd").read_text(encoding="utf-8")
    approval_index = text.index("Approve package installation? [Y/N]")

    for package in (
        "numpy",
        "matplotlib",
        "pymoo",
        "numba",
        "moocore",
        "cffi",
        "pycparser",
        "platformdirs",
        "pip",
        "setuptools",
    ):
        assert text.index(package) < approval_index


def test_windows_launcher_refreshes_setup_and_reports_acceleration_status() -> None:
    text = (ROOT / "launch_dot_gui.cmd").read_text(encoding="utf-8")

    assert ".dot_setup_v6" in text
    assert "struct.calcsize('P')*8==64" in text
    assert "sys.version_info[:2] in ((3,11),(3,12),(3,13))" in text
    assert "from dot.acceleration import jit_status" in text
    assert "DOT acceleration:" in text
