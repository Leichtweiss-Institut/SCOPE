"""
QGIS plugin entry point for SCOPE.

This module defines the plugin class that QGIS instantiates via
``classFactory`` in ``__init__.py``. It adds a toolbar button and a menu
entry under the Plugins menu and shows the main dialog when triggered.
"""
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


class ScopePlugin:
    """Wires SCOPE into the QGIS GUI."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.action = None
        self.dialog = None
        self.menu_title = "&SCOPE"

    def initGui(self):
        """Create the toolbar button and menu entry (called by QGIS)."""
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(icon, "SCOPE", self.iface.mainWindow())
        self.action.setToolTip("Generate orthogonal grids for XBeach / AeoLiS")
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.menu_title, self.action)

    def unload(self):
        """Remove the toolbar button and menu entry (called by QGIS)."""
        if self.action is not None:
            self.iface.removePluginMenu(self.menu_title, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

        if self.dialog is not None:
            self.dialog.close()
            self.dialog = None

    def run(self):
        """Show the main dialog, reusing the existing instance if open."""
        from .gui.main_dialog import ScopeDialog
        from .gui.welcome_dialog import show_welcome_if_needed

        if self.dialog is None:
            if not show_welcome_if_needed(self.iface.mainWindow()):
                return

            self.dialog = ScopeDialog()
            # Build a fresh dialog next time once this one is destroyed.
            self.dialog.destroyed.connect(self._on_dialog_destroyed)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _on_dialog_destroyed(self, *args):
        self.dialog = None
