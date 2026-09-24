"""
Launcher for SCOPE.

This script can be executed from the QGIS Python console to launch the tool.
It handles path configuration and provides error reporting.
"""

import os
import sys
import traceback
import importlib
from qgis.utils import iface
from qgis.core import Qgis

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

tool_dir = os.path.dirname(os.path.abspath(__file__))
if tool_dir not in sys.path:
    sys.path.append(tool_dir)

def show_message(text, level=Qgis.MessageLevel.Info, duration=5):
    """Display a message in the QGIS message bar."""
    if iface:
        iface.messageBar().pushMessage("SCOPE", text, level, duration)  # type: ignore
    else:
        print(text)

try:
    # Clear any cached imports first
    modules_to_reload = [
        'SCOPE.gui.welcome_dialog',
        'SCOPE.gui.main_dialog',
        'SCOPE.main'
    ]

    for module_name in modules_to_reload:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
            show_message(f"Reloaded module: {module_name}", Qgis.MessageLevel.Info, 2)

    show_message("Loading SCOPE...", Qgis.MessageLevel.Info, 3)
    from SCOPE.main import run  # type: ignore

    run()

except ImportError as e:
    error_msg = f"Import error: {str(e)}"
    show_message(error_msg, Qgis.MessageLevel.Critical, 10)
    traceback.print_exc()

    print("\nPython path:")
    for p in sys.path:
        print(f"  {p}")
    print(f"\nScript directory: {os.path.abspath(__file__)}")

except Exception as e:
    error_msg = f"Error launching SCOPE: {str(e)}"
    show_message(error_msg, Qgis.MessageLevel.Critical, 10)
    traceback.print_exc()
