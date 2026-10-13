"""
Make the plugin importable as the package ``scope``, whatever the clone folder is called.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if "scope" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "scope", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["scope"] = module
    spec.loader.exec_module(module)
