"""
Welcome screen shown when SCOPE is launched.

A "Don't show this again" checkbox persists the choice via QSettings.
"""
import os

from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtGui import QPixmap, QFont, QFontMetrics
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QFrame, QSpacerItem, QSizePolicy
)

# QSettings key used to remember the "Don't show again" preference.
_SETTINGS_KEY = "SCOPE/show_welcome"

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class WelcomeDialog(QDialog):
    """Introductory splash describing SCOPE and its capabilities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to SCOPE")
        self.setMinimumWidth(540)
        self._build_ui()

    @staticmethod
    def should_show() -> bool:
        """Return True unless the user opted out previously."""
        value = QSettings().value(_SETTINGS_KEY, True)
        # QSettings may return strings ("false") depending on platform.
        if isinstance(value, str):
            return value.lower() not in ("false", "0", "no")
        return bool(value)

    @staticmethod
    def reset_preference() -> None:
        """Re-enable the welcome screen for future launches."""
        QSettings().setValue(_SETTINGS_KEY, True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        # Icon scaled to the title font height.
        title_font = QFont()
        title_font.setPointSize(26)
        title_font.setBold(True)

        title = QLabel("SCOPE")
        title.setFont(title_font)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addStretch(1)

        icon_path = os.path.join(_PLUGIN_ROOT, "icon.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            icon_label = QLabel()
            font_height = QFontMetrics(title_font).height()
            icon_label.setPixmap(
                pixmap.scaledToHeight(font_height, Qt.SmoothTransformation)
            )
            header.addWidget(icon_label)

        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        tagline = QLabel("Spatial Coastal Operations and Processing Engine")
        tagline.setStyleSheet("font-size: 12pt; color: #5a6b7b;")
        tagline.setAlignment(Qt.AlignHCenter)
        layout.addWidget(tagline)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Description. Uses <br> rather than "\n" because the bold tags make
        # Qt render this as rich text, where newlines collapse to spaces.
        description = QLabel(
            "SCOPE is a QGIS tool for turning raster bathymetry and vector "
            "layers into model-ready, orthogonal grid files for "
            "coastal models such as <b>XBeach</b> and <b>AeoLiS</b>.<br><br>"
            "Draw and rotate a model extent on the map, then export the grids "
            "your model needs."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 10.5pt;")
        layout.addWidget(description)

        bullets = QLabel(
            "<ul style='margin-left:-18px;'>"
            "<li>Export <b>x.grd, y.grd, z.grd</b> from raster datasets</li>"
            "<li>Create custom grid files (e.g. <b>veg.grd</b>, <b>ne_layer.grd</b>, "
            "<b>bedfriction.grd</b>) from polygon layers</li>"
            "<li>Build complex-valued <b>threshold mask</b> grids for AeoLiS</li>"
            "<li>Adaptive cross-shore resolution, local or world coordinates</li>"
            "<li>Model-area splitting and batch processing of multiple rasters</li>"
            "</ul>"
        )
        bullets.setTextFormat(Qt.RichText)
        bullets.setWordWrap(True)
        bullets.setStyleSheet("font-size: 10.5pt;")
        layout.addWidget(bullets)

        layout.addSpacerItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Expanding))

        footer = QHBoxLayout()
        self.dont_show_checkbox = QCheckBox("Don't show this again")
        footer.addWidget(self.dont_show_checkbox)
        footer.addStretch(1)

        start_button = QPushButton("Get started")
        start_button.setDefault(True)
        start_button.clicked.connect(self._on_start)
        footer.addWidget(start_button)

        layout.addLayout(footer)

    def _on_start(self):
        """Persist the preference and close the welcome screen."""
        if self.dont_show_checkbox.isChecked():
            QSettings().setValue(_SETTINGS_KEY, False)
        self.accept()


def show_welcome_if_needed(parent=None) -> bool:
    """Show the welcome screen unless the user opted out.

    Returns True if the main dialog should open, False if the user closed the
    welcome screen without clicking "Get started".
    """
    if not WelcomeDialog.should_show():
        return True
    dialog = WelcomeDialog(parent)
    return dialog.exec_() == QDialog.Accepted
