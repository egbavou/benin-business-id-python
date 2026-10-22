import ast
import subprocess
import sys
from pathlib import Path

OPTIONAL_PACKAGES = {"httpx", "django", "pydantic", "pydantic_core"}
PACKAGE = Path(__file__).resolve().parents[2] / "src" / "benin_business_id"


def test_importing_the_core_loads_no_optional_package() -> None:
    code = (
        "import sys, benin_business_id; "
        f"print(sorted(set({sorted(OPTIONAL_PACKAGES)!r}) & set(sys.modules)))"
    )
    output = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    ).stdout

    assert output.strip() == "[]"


def test_core_modules_import_optional_packages_lazily_only() -> None:
    for module in PACKAGE.glob("_*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))

        for node in tree.body:
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue

            assert names.isdisjoint(OPTIONAL_PACKAGES), f"{module.name} imports {names}"
