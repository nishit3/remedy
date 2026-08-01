"""Manual check that the tool layer works before any agent touches it.

    python tests/test_tools_manual.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from remedy.tools import read_file, search_code, apply_edit, run_tests


def main():
    tmp = Path(tempfile.mkdtemp(prefix="remedy_smoke_"))
    print(f"working in {tmp}")

    # tiny repo with one bug: add() subtracts instead of adding
    (tmp / "calc.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n"
    )
    (tmp / "test_calc.py").write_text(
        "from calc import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    )

    test_cmd = f"{sys.executable} -m pytest test_calc.py -q"

    r = read_file(tmp / "calc.py")
    assert r.success
    print("read_file ok")

    s = search_code("def add", tmp)
    print(f"search_code ok, matches={s.matches}" if s.success else f"search_code skipped: {s.message}")

    result = run_tests(tmp, test_cmd)
    assert not result.passed, "should fail before the fix"
    print("run_tests ok (correctly failed)")

    edit = apply_edit(tmp / "calc.py", search="return a - b", replace="return a + b")
    assert edit.success, edit.message
    print("apply_edit ok")

    result = run_tests(tmp, test_cmd)
    assert result.passed, "should pass after the fix"
    print("run_tests ok (correctly passed after fix)")

    print("\nall four tools verified end-to-end")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
