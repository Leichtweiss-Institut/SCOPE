"""
The computational modules must stay importable without QGIS.
"""
import importlib
import sys


def test_core_modules_do_not_import_qgis():
    for name in ("scope.processing.grid.gridmath", "scope.processing.grid.threshold"):
        importlib.import_module(name)
    assert "qgis" not in sys.modules
