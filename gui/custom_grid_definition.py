"""
Custom grid definition dialog.

Lets the user define one custom grid file: output filename, default value,
output decimals, preview flag and a value per selected polygon layer.
"""
from qgis.PyQt.QtCore import QLocale
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox,
    QCheckBox, QComboBox, QLineEdit, QWidget, QScrollArea, QMessageBox
)

from ..processing.custom_grid import CustomGridDefinition


# Presets pre-fill filename, default value and decimals; all fields stay editable.
PRESETS = [
    ("Custom", "", 0.0, 3),
    ("Vegetation density (veg.grd)", "veg.grd", 0.0, 3),
    ("Vegetation type (veg_type.grd)", "veg_type.grd", 0.0, 0),
    ("Hard layer (ne_layer.grd)", "ne_layer.grd", 0.0, 3),
    ("Bed friction (bedfriction.grd)", "bedfriction.grd", 0.0, 3),
]

VALUE_RANGE = (-999999.0, 999999.0)


class CustomGridDefinitionDialog(QDialog):
    """Dialog for defining a custom grid file from polygon layers."""

    def __init__(self, vector_layers, definition=None, parent=None):
        super().__init__(parent)
        # Use '.' as the decimal separator in all numeric fields.
        self.setLocale(QLocale.c())
        self.vector_layers = vector_layers
        self._definition = definition
        self.setWindowTitle("Define custom grid file")
        self.setMinimumSize(520, 620)
        self.setup_ui()
        if definition is not None:
            self._load_definition(definition)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Title and instructions
        title = QLabel("Custom grid file")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        instructions = QLabel(
            "Define a grid file built from polygon layers: cells covered by a "
            "layer get that layer's value, all other cells get the default value. "
            "Later layers override earlier ones where they overlap."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Grid file settings
        settings_group = QGroupBox("Grid file settings")
        settings_layout = QFormLayout(settings_group)

        self.preset_combo = QComboBox()
        for label, _filename, _default, _decimals in PRESETS:
            self.preset_combo.addItem(label)
        self.preset_combo.setToolTip(
            "Pre-fills filename, default value and decimals for common model files"
        )
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        settings_layout.addRow("Preset:", self.preset_combo)

        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("e.g. veg.grd")
        self.filename_edit.setToolTip(
            "Output file name; '.grd' is appended when no extension is given"
        )
        settings_layout.addRow("Filename:", self.filename_edit)

        self.default_spin = QDoubleSpinBox()
        self.default_spin.setRange(*VALUE_RANGE)
        self.default_spin.setDecimals(3)
        self.default_spin.setValue(0.0)
        self.default_spin.setToolTip("Value for cells not covered by any selected layer")
        settings_layout.addRow("Default value:", self.default_spin)

        self.decimals_spin = QSpinBox()
        self.decimals_spin.setRange(0, 10)
        self.decimals_spin.setValue(3)
        self.decimals_spin.setToolTip(
            "Decimal places in the output file (0 writes integers)"
        )
        self.decimals_spin.valueChanged.connect(self._update_value_decimals)
        settings_layout.addRow("Decimals:", self.decimals_spin)

        self.preview_cb = QCheckBox("Show preview pane after processing")
        self.preview_cb.setChecked(True)
        settings_layout.addRow("", self.preview_cb)

        layout.addWidget(settings_group)

        # Column headers for the layer list.
        header_row = QHBoxLayout()
        header_layer = QLabel("Layer")
        header_value = QLabel("Value")
        for lbl in (header_layer, header_value):
            lbl.setStyleSheet("font-weight: bold;")
        header_row.addWidget(header_layer, 3)
        header_row.addWidget(header_value, 1)
        layout.addLayout(header_row)

        # Scrollable area for layer selection
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        self.layer_widgets = []
        for layer in self.vector_layers:
            layer_widget = QHBoxLayout()

            checkbox = QCheckBox(layer.name())

            value_spin = QDoubleSpinBox()
            value_spin.setRange(*VALUE_RANGE)
            value_spin.setDecimals(3)
            value_spin.setValue(0.0)
            value_spin.setToolTip("Value assigned to cells covered by this layer")

            layer_widget.addWidget(checkbox, 3)
            layer_widget.addWidget(value_spin, 1)

            widget_container = QWidget()
            widget_container.setLayout(layer_widget)
            scroll_layout.addWidget(widget_container)

            self.layer_widgets.append((checkbox, value_spin, layer))

        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        apply_default_btn = QPushButton("Apply default value to all layers")
        apply_default_btn.clicked.connect(self.apply_default_to_all)
        layout.addWidget(apply_default_btn)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        ok_btn.clicked.connect(self._on_accept)
        cancel_btn.clicked.connect(self.reject)

    def _apply_preset(self, index):
        """Fill filename, default value and decimals from the chosen preset."""
        _label, filename, default_value, decimals = PRESETS[index]
        self.filename_edit.setText(filename)
        self.default_spin.setValue(default_value)
        self.decimals_spin.setValue(decimals)

    def _update_value_decimals(self, decimals):
        """Match the input spinboxes' precision to the output decimals."""
        self.default_spin.setDecimals(decimals)
        for _checkbox, value_spin, _layer in self.layer_widgets:
            value_spin.setDecimals(decimals)

    def _load_definition(self, definition):
        """Pre-fill all fields from an existing definition (edit mode)."""
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)  # "Custom"
        self.preset_combo.blockSignals(False)

        self.filename_edit.setText(definition.filename)
        self.decimals_spin.setValue(definition.decimals)
        self.default_spin.setValue(definition.default_value)
        self.preview_cb.setChecked(definition.show_preview)

        values_by_id = {
            layer.id(): value for layer, value in definition.valid_layer_values().items()
        }
        for checkbox, value_spin, layer in self.layer_widgets:
            if layer.id() in values_by_id:
                checkbox.setChecked(True)
                value_spin.setValue(values_by_id[layer.id()])

    def _on_accept(self):
        """Validate the filename before closing the dialog."""
        name = self.filename_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing filename",
                                "Please enter an output filename (e.g. veg.grd).")
            return
        if "/" in name or "\\" in name:
            QMessageBox.warning(self, "Invalid filename",
                                "The filename must not contain path separators.")
            return
        self.accept()

    def apply_default_to_all(self):
        """Apply the default value to all layer rows."""
        default_val = self.default_spin.value()
        for _checkbox, value_spin, _layer in self.layer_widgets:
            value_spin.setValue(default_val)

    def get_definition(self):
        """Return a CustomGridDefinition built from the dialog state."""
        layer_values = {}
        for checkbox, value_spin, layer in self.layer_widgets:
            if checkbox.isChecked():
                layer_values[layer] = value_spin.value()
        return CustomGridDefinition(
            filename=self.filename_edit.text().strip(),
            layer_values=layer_values,
            default_value=self.default_spin.value(),
            decimals=self.decimals_spin.value(),
            enabled=self._definition.enabled if self._definition is not None else True,
            show_preview=self.preview_cb.isChecked(),
        )
