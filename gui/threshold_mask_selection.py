"""
Threshold mask layer selection dialog for AeoLiS.
"""
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QGroupBox, QFormLayout, QDoubleSpinBox,
    QCheckBox, QWidget, QScrollArea
)


class ThresholdMaskSelectionDialog(QDialog):
    """Dialog for selecting polygon layers and assigning complex velocity threshold values for AeoLiS."""

    def __init__(self, vector_layers, default_real=9.0, default_imag=0.0):
        super().__init__()
        self.vector_layers = vector_layers
        self.default_real = default_real
        self.default_imag = default_imag
        self.setWindowTitle("Select threshold mask layers")
        self.setMinimumSize(500, 650)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Title and instructions
        title = QLabel("Threshold mask Layer Selection")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        instructions = QLabel(
            "Select polygon layers and assign complex velocity threshold values for AeoLiS.\n"
            "Real part: velocity threshold multiplier (>1.0 increases threshold, protecting vegetation)\n"
            "Imaginary part: additive offset (usually 0.0)\n"
            "Areas not covered by any polygon will have default values (1.0+0.0j)."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("margin: 10px; padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(instructions)

        # Default value settings
        default_group = QGroupBox("Default settings")
        default_layout = QFormLayout(default_group)

        self.default_real_spin = QDoubleSpinBox()
        self.default_real_spin.setRange(0.0, 20.0)
        self.default_real_spin.setDecimals(3)
        self.default_real_spin.setValue(self.default_real)
        self.default_real_spin.setToolTip("Velocity threshold multiplier for areas outside polygons")
        default_layout.addRow("Default real part:", self.default_real_spin)

        self.default_imag_spin = QDoubleSpinBox()
        self.default_imag_spin.setRange(-10.0, 10.0)
        self.default_imag_spin.setDecimals(3)
        self.default_imag_spin.setValue(self.default_imag)
        self.default_imag_spin.setToolTip("Additive offset (usually 0.0)")
        default_layout.addRow("Default imaginary part:", self.default_imag_spin)

        apply_default_btn = QPushButton("Apply to all layers")
        apply_default_btn.clicked.connect(self.apply_default_to_all)
        default_layout.addRow("", apply_default_btn)

        layout.addWidget(default_group)

        # Scrollable area for layer selection
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Header for the table-like layout
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.addWidget(QLabel("Layer name"))
        header_layout.addWidget(QLabel("Real part"))
        header_layout.addWidget(QLabel("Imaginary part"))
        header_layout.setContentsMargins(20, 5, 5, 5)
        scroll_layout.addWidget(header_widget)

        self.layer_widgets = []
        for layer in self.vector_layers:
            layer_widget = QHBoxLayout()

            checkbox = QCheckBox(layer.name())
            checkbox.setMinimumWidth(200)

            real_spin = QDoubleSpinBox()
            real_spin.setRange(0.0, 20.0)
            real_spin.setDecimals(3)
            real_spin.setValue(self.default_real)
            real_spin.setToolTip("Velocity threshold multiplier (>1.0 increases threshold, protecting vegetation)")
            real_spin.setMinimumWidth(100)

            imag_spin = QDoubleSpinBox()
            imag_spin.setRange(-10.0, 10.0)
            imag_spin.setDecimals(3)
            imag_spin.setValue(self.default_imag)
            imag_spin.setToolTip("Additive offset (usually 0.0)")
            imag_spin.setMinimumWidth(100)

            layer_widget.addWidget(checkbox)
            layer_widget.addWidget(real_spin)
            layer_widget.addWidget(imag_spin)
            layer_widget.addStretch()

            widget_container = QWidget()
            widget_container.setLayout(layer_widget)
            scroll_layout.addWidget(widget_container)

            self.layer_widgets.append((checkbox, real_spin, imag_spin, layer))

        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # Common values section
        common_group = QGroupBox("Common threshold mask values")
        common_layout = QVBoxLayout(common_group)

        common_info = QLabel(
            "Common values for different scenarios:\n"
            "• Saltwater meadows: 9.0+0.0j (higher velocity threshold for protection)\n"
            "• Strong protection: 15.0+0.0j (very high velocity threshold)\n"
            "• Moderate protection: 5.0+0.0j (moderate velocity threshold increase)\n"
            "• Normal conditions: 1.0+0.0j (no change to velocity threshold)"
        )
        common_info.setStyleSheet("background-color: #f9f9f9; padding: 5px; border-radius: 3px;")
        common_layout.addWidget(common_info)

        # Quick-set buttons
        quick_buttons_layout = QHBoxLayout()

        meadow_btn = QPushButton("Set meadow (9.0+0j)")
        meadow_btn.clicked.connect(lambda: self.set_selected_values(9.0, 0.0))
        quick_buttons_layout.addWidget(meadow_btn)

        strong_btn = QPushButton("Set strong (15.0+0j)")
        strong_btn.clicked.connect(lambda: self.set_selected_values(15.0, 0.0))
        quick_buttons_layout.addWidget(strong_btn)

        moderate_btn = QPushButton("Set moderate (5.0+0j)")
        moderate_btn.clicked.connect(lambda: self.set_selected_values(5.0, 0.0))
        quick_buttons_layout.addWidget(moderate_btn)

        normal_btn = QPushButton("Set normal (1.0+0j)")
        normal_btn.clicked.connect(lambda: self.set_selected_values(1.0, 0.0))
        quick_buttons_layout.addWidget(normal_btn)

        common_layout.addLayout(quick_buttons_layout)
        layout.addWidget(common_group)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def apply_default_to_all(self):
        """Apply default values to all layer spin boxes."""
        default_real = self.default_real_spin.value()
        default_imag = self.default_imag_spin.value()
        for checkbox, real_spin, imag_spin, layer in self.layer_widgets:
            real_spin.setValue(default_real)
            imag_spin.setValue(default_imag)

    def set_selected_values(self, real_val, imag_val):
        """Set values for all checked layers."""
        for checkbox, real_spin, imag_spin, layer in self.layer_widgets:
            if checkbox.isChecked():
                real_spin.setValue(real_val)
                imag_spin.setValue(imag_val)

    def get_selected_layers(self):
        """Return dictionary of selected layers and their complex values."""
        selected = {}
        for checkbox, real_spin, imag_spin, layer in self.layer_widgets:
            if checkbox.isChecked():
                real_part = real_spin.value()
                imag_part = imag_spin.value()
                complex_value = complex(real_part, imag_part)
                selected[layer] = complex_value
        return selected

    def get_default_value(self):
        """Return the default complex value for non-overlapping cells."""
        real_part = self.default_real_spin.value()
        imag_part = self.default_imag_spin.value()
        return complex(real_part, imag_part)
