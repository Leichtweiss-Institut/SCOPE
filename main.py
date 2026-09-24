"""
Main module for SCOPE.
"""
import traceback
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from qgis.utils import iface  # type: ignore
from qgis.core import Qgis

from SCOPE.gui.main_dialog import ScopeDialog # type: ignore


scope_dialog = None


def msg(text: str, level: Qgis.MessageLevel = Qgis.MessageLevel.Info, dur: int = 5) -> None:
    """Display a message in the QGIS message bar."""
    iface.messageBar().pushMessage("SCOPE", text, level, dur)  # type: ignore


def run():
    """Main entry point for SCOPE."""
    global scope_dialog
    try:
        from SCOPE.gui.welcome_dialog import show_welcome_if_needed
        if not show_welcome_if_needed():
            return

        scope_dialog = ScopeDialog()
        scope_dialog.show()
        msg("SCOPE launched. Use the GUI to configure and process grids.", Qgis.MessageLevel.Info, 5)
    except Exception as exc:
        msg(f"Cannot launch SCOPE: {exc}", Qgis.MessageLevel.Critical, 0)
        traceback.print_exc()
