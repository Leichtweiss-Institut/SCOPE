"""
The computational modules must stay importable without QGIS.
"""
import importlib
import sys


def test_core_modules_do_not_import_qgis():
    for name in ("scope.processing.grid.gridmath", "scope.processing.grid.threshold",
                 "scope.processing.grid.stream", "scope.processing.grid.estimate",
                 "scope.processing.progress"):
        importlib.import_module(name)
    assert "qgis" not in sys.modules
