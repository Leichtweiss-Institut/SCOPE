"""
Launcher for SCOPE.

Run from the QGIS Python console editor, or from the console with:

    path = '/path/to/SCOPE/launcher.py'
    exec(open(path).read(), {'__file__': path})

The package is imported under the name of its folder, so a checkout named
"SCOPE-main" works as well. All SCOPE modules are reloaded on every run, so
code changes take effect without restarting QGIS.
"""

import importlib
import os
import sys
import traceback

from qgis.core import Qgis
from qgis.utils import iface

tool_dir = os.path.dirname(os.path.abspath(__file__))
package_name = os.path.basename(tool_dir)
parent_dir = os.path.dirname(tool_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


def show_message(text, level=Qgis.MessageLevel.Info, duration=5):
    """Display a message in the QGIS message bar."""
    if iface:
        iface.messageBar().pushMessage("SCOPE", text, level, duration)  # type: ignore
    else:
        print(text)


try:
    # Drop cached modules so edited files are imported fresh.
    for name in list(sys.modules):
        if name == package_name or name.startswith(package_name + "."):
            del sys.modules[name]

    show_message("Loading SCOPE...", Qgis.MessageLevel.Info, 3)
    importlib.import_module(f"{package_name}.main").run()

except ImportError as e:
    show_message(f"Import error: {e}", Qgis.MessageLevel.Critical, 10)
    traceback.print_exc()
    print(f"\nPackage '{package_name}' expected in: {parent_dir}")

except Exception as e:
    show_message(f"Error launching SCOPE: {e}", Qgis.MessageLevel.Critical, 10)
    traceback.print_exc()
