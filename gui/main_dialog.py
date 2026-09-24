"""
Main GUI dialog for SCOPE.
"""
import os
from pathlib import Path
from qgis.PyQt.QtCore import Qt, QLocale
from qgis.PyQt.QtGui import QPixmap, QFont, QFontMetrics
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QGroupBox, QFormLayout, QDoubleSpinBox,
    QCheckBox, QMessageBox, QProgressBar, QTextEdit, QComboBox, QWidget, QSpinBox, QFileDialog,
    QListWidget, QListWidgetItem
)
from qgis.utils import iface
from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.gui import QgsProjectionSelectionWidget

from SCOPE.utils.constants import set_working_crs, get_working_crs

from SCOPE.gui.raster_selection import select_raster_layers
from SCOPE.core.map_tools import RectTool, MoveModelAreaTool
from SCOPE.processing.raster import clip_translate_grid_gui


class AdaptiveGridDialog(QDialog):
    """Settings window for cross-shore adaptive grid resolution.

    Opened from the main dialog's "Use Adaptive Grid Resolution" button. Holds
    the enable toggle and the cross-shore refinement parameters; the main
    dialog reads these values when processing.
    """

    def __init__(self, default_longshore=10.0, parent=None):
        super().__init__(parent)
        # Use '.' as the decimal separator in all numeric fields.
        self.setLocale(QLocale.c())
        self.setWindowTitle("Adaptive grid resolution (cross-shore)")
        self.setMinimumWidth(360)
        self._build_ui(default_longshore)

    def _build_ui(self, default_longshore):
        layout = QVBoxLayout(self)

        self.enable_cb = QCheckBox("Use adaptive grid resolution (cross-shore)")
        self.enable_cb.setChecked(False)
        self.enable_cb.toggled.connect(self._on_toggle)
        layout.addWidget(self.enable_cb)

        # Settings live in their own widget so they can be enabled/disabled
        # as a group based on the checkbox.
        self.settings_widget = QWidget()
        form = QFormLayout(self.settings_widget)

        self.min_cell_size_spin = QDoubleSpinBox()
        self.min_cell_size_spin.setRange(0.1, 1000)
        self.min_cell_size_spin.setValue(2.0)
        self.min_cell_size_spin.setSuffix(" m")
        self.min_cell_size_spin.setToolTip("Finest cross-shore spacing (onshore)")
        form.addRow("Min Δx:", self.min_cell_size_spin)

        self.max_cell_size_spin = QDoubleSpinBox()
        self.max_cell_size_spin.setRange(0.1, 1000)
        self.max_cell_size_spin.setValue(20.0)
        self.max_cell_size_spin.setSuffix(" m")
        self.max_cell_size_spin.setToolTip("Coarsest cross-shore spacing (offshore)")
        form.addRow("Max Δx:", self.max_cell_size_spin)

        self.adaptive_threshold_spin = QDoubleSpinBox()
        self.adaptive_threshold_spin.setRange(-1000, 1000)
        self.adaptive_threshold_spin.setDecimals(3)
        self.adaptive_threshold_spin.setValue(3.5)
        self.adaptive_threshold_spin.setSuffix(" m")
        self.adaptive_threshold_spin.setToolTip(
            "Fine resolution is applied where the bed level is above this value"
        )
        form.addRow("Bed level threshold:", self.adaptive_threshold_spin)

        self.adaptive_longshore_size_spin = QDoubleSpinBox()
        self.adaptive_longshore_size_spin.setRange(0.1, 1000)
        self.adaptive_longshore_size_spin.setValue(default_longshore)
        self.adaptive_longshore_size_spin.setSuffix(" m")
        self.adaptive_longshore_size_spin.setToolTip(
            "Constant longshore spacing for adaptive mode"
        )
        form.addRow("Adaptive longshore Δy:", self.adaptive_longshore_size_spin)

        layout.addWidget(self.settings_widget)

        # Keep max >= min as the user edits values.
        self.min_cell_size_spin.valueChanged.connect(self._validate_cell_sizes)
        self.max_cell_size_spin.valueChanged.connect(self._validate_cell_sizes)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        button_row.addWidget(ok_btn)
        layout.addLayout(button_row)

        self._on_toggle(self.enable_cb.isChecked())

    def _on_toggle(self, checked):
        """Enable/disable the settings fields based on the checkbox."""
        self.settings_widget.setEnabled(checked)

    def _validate_cell_sizes(self):
        """Ensure the maximum cross-shore size stays above the minimum."""
        if self.max_cell_size_spin.value() <= self.min_cell_size_spin.value():
            self.max_cell_size_spin.setValue(self.min_cell_size_spin.value() * 2)

    def is_enabled(self) -> bool:
        """Return True if adaptive grid resolution is switched on."""
        return self.enable_cb.isChecked()


class ScopeDialog(QDialog):
    """Main dialog for SCOPE."""

    def __init__(self):
        super().__init__()
        # Use '.' as the decimal separator in all numeric fields.
        self.setLocale(QLocale.c())
        self.setWindowTitle("SCOPE")
        self.setMinimumSize(500, 600)        # Initialize attributes first
        self.selected_rasters = []
        self.selected_bathymetry = None
        self.selected_bathymetry_layers = []
        self.custom_grid_definitions = []  # List of CustomGridDefinition objects
        self.selected_threshold_layers = {}
        self.threshold_default_value = complex(1.0, 0.0)  # Default complex value for threshold mask
        self.current_geometry = None
        self.ll_point = None
        self.centre_point = None
        self.rect_tool = None
        self.move_tool = None

        self.split_areas = []  # List of sub-area geometries
        self.split_rows = 1
        self.split_cols = 1
        self.setup_ui()

        # Keep custom grid definitions free of layers removed from the project.
        QgsProject.instance().layersWillBeRemoved.connect(self._on_layers_removed)

        self.initialize_layer_visibility()

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)

        # Header: icon + "SCOPE" title on the left, "Show welcome screen" on
        # the right. The icon is scaled to the title font height so they match.
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 10, 10, 10)

        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icon.png"
        )
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            icon_label = QLabel()
            font_height = QFontMetrics(title_font).height()
            icon_label.setPixmap(
                pixmap.scaledToHeight(font_height, Qt.SmoothTransformation)
            )
            header_layout.addWidget(icon_label)

        title = QLabel("SCOPE")
        title.setFont(title_font)
        header_layout.addWidget(title)

        header_layout.addStretch(1)

        self.welcome_btn = QPushButton("Show welcome screen")
        self.welcome_btn.clicked.connect(self.show_welcome_screen)
        header_layout.addWidget(self.welcome_btn)

        layout.addLayout(header_layout)

        self._create_rectangle_group(layout)

        self._create_grid_group(layout)

        self._create_options_group(layout)

        self._create_preview_group(layout)

        self._create_action_buttons(layout)

        self._create_custom_grids_group(layout)

        self._create_log_area(layout)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Bottom action row: highlighted "Process selected area" on the left,
        # "Exit SCOPE" on the bottom right.
        bottom_row = QHBoxLayout()

        self.process_btn = QPushButton("Process selected area")
        self.process_btn.clicked.connect(self.process_area)
        self.process_btn.setEnabled(False)
        self.process_btn.setMinimumHeight(40)
        self.process_btn.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; "
            "font-size: 12pt; border-radius: 4px; padding: 6px; }"
            "QPushButton:hover:enabled { background-color: #357f38; }"
            "QPushButton:disabled { background-color: #b5b5b5; color: #eeeeee; }"
        )
        bottom_row.addWidget(self.process_btn, 3)

        exit_btn = QPushButton("Exit SCOPE")
        exit_btn.clicked.connect(self.close)
        exit_btn.setMinimumHeight(40)
        bottom_row.addWidget(exit_btn, 1)

        layout.addLayout(bottom_row)

        # Emphasize the section headers now that all groups exist.
        self._style_section_headers()

    def _style_section_headers(self):
        """Make section headers (QGroupBox titles) slightly larger (not bold).

        The box font sets the title size, while ``QGroupBox *`` resets
        descendant widgets back to the normal size.
        """
        base_size = self.font().pointSize()
        if base_size <= 0:
            base_size = 10
        self.setStyleSheet(
            "QGroupBox { font-size: %dpt; }"
            "QGroupBox * { font-size: %dpt; }"
            % (base_size + 2, base_size)
        )

    def _create_rectangle_group(self, parent_layout):
        """Create the model area parameters group."""
        rect_group = QGroupBox("Model area parameters")
        rect_layout = QFormLayout(rect_group)
        self.anchor_combo = QComboBox()
        self.anchor_combo.addItems(["Center", "XBeach coordinate origin"])
        self.anchor_combo.currentTextChanged.connect(self.on_anchor_point_changed)
        rect_layout.addRow("Anchor point:", self.anchor_combo)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 100000)
        self.width_spin.setValue(1000)
        self.width_spin.setSuffix(" m")
        rect_layout.addRow("Width:", self.width_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.1, 100000)
        self.height_spin.setValue(1000)
        self.height_spin.setSuffix(" m")
        rect_layout.addRow("Height:", self.height_spin)
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(0, 360)
        self.rotation_spin.setValue(0)
        self.rotation_spin.setSuffix("°")
        rect_layout.addRow("Rotation:", self.rotation_spin)

        parent_layout.addWidget(rect_group)

        model_area_button_layout = QHBoxLayout()

        self.draw_rect_btn = QPushButton("Create model area")
        self.draw_rect_btn.clicked.connect(self.start_rectangle_tool)
        model_area_button_layout.addWidget(self.draw_rect_btn)

        self.split_area_btn = QPushButton("Split model area")
        self.split_area_btn.clicked.connect(self.split_model_area)
        self.split_area_btn.setEnabled(False)  # Initially disabled
        model_area_button_layout.addWidget(self.split_area_btn)

        self.move_area_btn = QPushButton("Move model area")
        self.move_area_btn.clicked.connect(self.toggle_move_tool)
        self.move_area_btn.setEnabled(False)
        model_area_button_layout.addWidget(self.move_area_btn)

        parent_layout.addLayout(model_area_button_layout)
    def _create_grid_group(self, parent_layout):
        """Create the grid parameters group."""
        grid_group = QGroupBox("Grid parameters")
        grid_layout = QFormLayout(grid_group)

        self.dx_spin = QDoubleSpinBox()
        self.dx_spin.setRange(0.1, 1000)
        self.dx_spin.setValue(10)
        self.dx_spin.setSuffix(" m")
        self.dx_spin.setToolTip("Cross-shore grid spacing (used for uniform grids)")
        grid_layout.addRow("Cross-shore (Δx):", self.dx_spin)

        self.dy_spin = QDoubleSpinBox()
        self.dy_spin.setRange(0.1, 1000)
        self.dy_spin.setValue(10)
        self.dy_spin.setSuffix(" m")
        self.dy_spin.setToolTip("Longshore grid spacing (used for uniform grids)")
        grid_layout.addRow("Longshore (Δy):", self.dy_spin)

        # Adaptive settings are edited in a separate dialog opened by this button.
        self.adaptive_dialog = AdaptiveGridDialog(
            default_longshore=self.dy_spin.value(), parent=self
        )
        self.adaptive_btn = QPushButton("Use adaptive grid resolution (cross-shore)")
        self.adaptive_btn.setToolTip(
            "Configure cross-shore adaptive grid resolution settings"
        )
        self.adaptive_btn.clicked.connect(self.open_adaptive_dialog)
        grid_layout.addRow("", self.adaptive_btn)

        parent_layout.addWidget(grid_group)

    def _create_preview_group(self, parent_layout):
        """Create the 'Enable preview panes' group with one toggle per preview.

        Each checkbox maps to a distinct matplotlib window opened after grid
        generation. Laid out in two columns to save vertical space.
        """
        preview_group = QGroupBox("Enable preview panes")
        preview_layout = QGridLayout(preview_group)

        self.preview_spacing_cb = QCheckBox("Grid spacing (cross-shore Δx)")
        self.preview_spacing_cb.setChecked(True)
        self.preview_spacing_cb.setToolTip(
            "Map of cross-shore cell size Δx with a thinned grid overlay"
        )

        self.preview_bed2d_cb = QCheckBox("Bed level (2D terrain)")
        self.preview_bed2d_cb.setChecked(True)
        self.preview_bed2d_cb.setToolTip(
            "2D terrain colormap of the interpolated bed level (z.grd)"
        )

        self.preview_bed3d_cb = QCheckBox("Bed level (3D terrain)")
        self.preview_bed3d_cb.setChecked(True)
        self.preview_bed3d_cb.setToolTip(
            "3D surface plot of the interpolated bed level"
        )

        self.preview_custom_cb = QCheckBox("Custom grid files")
        self.preview_custom_cb.setChecked(True)
        self.preview_custom_cb.setToolTip(
            "Master switch: one preview window per custom grid file whose own\n"
            "'Show preview' flag is enabled"
        )

        # Two columns: spacing / bed-2D on the left, bed-3D / custom grids right.
        preview_layout.addWidget(self.preview_spacing_cb, 0, 0)
        preview_layout.addWidget(self.preview_bed3d_cb, 0, 1)
        preview_layout.addWidget(self.preview_bed2d_cb, 1, 0)
        preview_layout.addWidget(self.preview_custom_cb, 1, 1)

        parent_layout.addWidget(preview_group)

    def open_adaptive_dialog(self):
        """Open the adaptive grid settings dialog and reflect its state."""
        self.adaptive_dialog.exec_()
        self._update_adaptive_button_label()

    def _update_adaptive_button_label(self):
        """Update the adaptive button to show whether adaptive mode is on."""
        if self.adaptive_dialog.is_enabled():
            self.adaptive_btn.setText("Adaptive grid resolution (cross-shore): on")
            self.adaptive_btn.setStyleSheet("font-weight: bold;")
        else:
            self.adaptive_btn.setText("Use adaptive grid resolution (cross-shore)")
            self.adaptive_btn.setStyleSheet("")

    def _create_options_group(self, parent_layout):
        """Create the processing options group."""
        options_group = QGroupBox("Processing options")
        options_layout = QVBoxLayout(options_group)

        self.create_grids_cb = QCheckBox("Create grid files (x.grd, y.grd, z.grd)")
        self.create_grids_cb.setChecked(True)
        options_layout.addWidget(self.create_grids_cb)

        coord_layout = QHBoxLayout()
        coord_label = QLabel("Coordinate system:")
        self.coord_combo = QComboBox()
        self.coord_combo.addItems(["Local coordinates", "World coordinates"])
        self.coord_combo.setCurrentIndex(1)  # Make World coordinates the default
        self.coord_combo.setToolTip("Local: Origin at model area corner\nWorld: Real-world coordinates in the working CRS")
        coord_layout.addWidget(coord_label)
        coord_layout.addWidget(self.coord_combo)
        options_layout.addLayout(coord_layout)

        # Working CRS selector (defaults to the current project CRS).
        crs_layout = QHBoxLayout()
        crs_label = QLabel("Working CRS:")
        self.crs_widget = QgsProjectionSelectionWidget()
        # Hide the built-in quick-pick entries that confuse the choice; keep
        # just the project CRS shortcut and an explicitly chosen CRS.
        self.crs_widget.setOptionVisible(QgsProjectionSelectionWidget.DefaultCrs, False)
        self.crs_widget.setOptionVisible(QgsProjectionSelectionWidget.LayerCrs, False)
        self.crs_widget.setOptionVisible(QgsProjectionSelectionWidget.CrsNotSet, False)
        project_crs = QgsProject.instance().crs()
        if project_crs.isValid():
            self.crs_widget.setCrs(project_crs)
        self.crs_widget.setToolTip(
            "CRS used for processing and world-coordinate output.\n"
            "Defaults to the QGIS project CRS; pick another if needed."
        )
        crs_layout.addWidget(crs_label)
        crs_layout.addWidget(self.crs_widget)
        options_layout.addLayout(crs_layout)

        parent_layout.addWidget(options_group)

    def _create_action_buttons(self, parent_layout):
        """Create the action buttons."""
        button_layout = QVBoxLayout()

        raster_button_layout = QHBoxLayout()

        self.select_bathymetry_btn = QPushButton("Select bathymetry data")
        self.select_bathymetry_btn.clicked.connect(self.select_bathymetry)
        raster_button_layout.addWidget(self.select_bathymetry_btn)

        button_layout.addLayout(raster_button_layout)

        threshold_button_layout = QHBoxLayout()

        self.select_threshold_btn = QPushButton("Threshold mask")
        self.select_threshold_btn.clicked.connect(self.select_threshold_layers)
        self.select_threshold_btn.setToolTip("Select polygon layers for AeoLiS threshold masking (saltwater meadows, protected areas, etc.)")
        threshold_button_layout.addWidget(self.select_threshold_btn)

        button_layout.addLayout(threshold_button_layout)

        parent_layout.addLayout(button_layout)

    def _create_custom_grids_group(self, parent_layout):
        """Create the 'Custom grid files' group.

        Each list entry is one user-defined grid file built from polygon
        layers (e.g. veg.grd, ne_layer.grd, bedfriction.grd). The item
        checkbox enables/disables the grid without deleting its definition.
        """
        custom_group = QGroupBox("Custom grid files")
        custom_layout = QVBoxLayout(custom_group)

        info_label = QLabel(
            "Value grids built from polygon layers overlapping the model area "
            "(e.g. vegetation, hard layers, bed friction):"
        )
        info_label.setWordWrap(True)
        custom_layout.addWidget(info_label)

        self.custom_grid_list = QListWidget()
        self.custom_grid_list.setToolTip(
            "Checked grids are generated during processing; double-click to edit"
        )
        self.custom_grid_list.itemDoubleClicked.connect(lambda _item: self.edit_custom_grid())
        self.custom_grid_list.itemChanged.connect(self._on_custom_grid_item_changed)
        custom_layout.addWidget(self.custom_grid_list)

        button_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.setToolTip("Define a new custom grid file")
        add_btn.clicked.connect(self.add_custom_grid)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self.edit_custom_grid)
        duplicate_btn = QPushButton("Duplicate")
        duplicate_btn.setToolTip("Copy the selected grid (same layers) as a starting point")
        duplicate_btn.clicked.connect(self.duplicate_custom_grid)
        remove_btn = QPushButton("− Remove")
        remove_btn.clicked.connect(self.remove_custom_grid)
        for btn in (add_btn, edit_btn, duplicate_btn, remove_btn):
            button_row.addWidget(btn)
        custom_layout.addLayout(button_row)

        parent_layout.addWidget(custom_group)

    def _create_log_area(self, parent_layout):
        """Create the log/status area."""
        parent_layout.addWidget(QLabel("Log:"))

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setPlaceholderText("Processing log will appear here...")
        parent_layout.addWidget(self.log_text)

    def log(self, message):
        """Add message to log area with immediate UI update."""
        if hasattr(self, 'log_text') and self.log_text is not None:
            self.log_text.append(message)
            self.log_text.repaint()
            QgsApplication.processEvents()
        if str(message).startswith("WARNING:"):
            iface.messageBar().pushMessage("SCOPE", str(message)[len("WARNING:"):].strip(), Qgis.Warning, 8)

    def select_bathymetry(self):
        """Select a single raster layer for bathymetry data."""

        selected = select_raster_layers()
        if selected:
            self.selected_bathymetry_layers = selected
            self.selected_bathymetry = selected[0]
            if len(selected) == 1:
                self.log(f"Selected bathymetry: {self.selected_bathymetry.name()}")
                self.select_bathymetry_btn.setText(f"Bathymetry: {self.selected_bathymetry.name()}")
            else:
                names = ", ".join(layer.name() for layer in selected)
                self.log(f"Selected {len(selected)} bathymetry rasters for batch processing: {names}")
                self.select_bathymetry_btn.setText(f"Bathymetry: {len(selected)} rasters")
            self._update_process_button_state()
        else:
            self.log("No bathymetry data selected.")
            self.selected_bathymetry_layers = []
            self.selected_bathymetry = None
            self.select_bathymetry_btn.setText("Select bathymetry data")

    def _get_project_vector_layers(self):
        """Return all vector layers currently loaded in the project."""
        project = QgsProject.instance()
        return [
            layer for layer in project.mapLayers().values()
            if hasattr(layer, 'type') and layer.type() == layer.VectorLayer
        ]

    def add_custom_grid(self):
        """Define a new custom grid file."""
        from SCOPE.gui.custom_grid_definition import CustomGridDefinitionDialog

        vector_layers = self._get_project_vector_layers()
        if not vector_layers:
            self.log("No vector layers found for custom grid definition.")
            return

        dialog = CustomGridDefinitionDialog(vector_layers, parent=self)
        if dialog.exec_() == dialog.Accepted:
            definition = dialog.get_definition()
            self.custom_grid_definitions.append(definition)
            self._refresh_custom_grid_list()
            self.log(f"Added custom grid file '{definition.sanitized_filename()}' "
                     f"({len(definition.layer_values)} layers).")

    def edit_custom_grid(self):
        """Edit the selected custom grid definition."""
        from SCOPE.gui.custom_grid_definition import CustomGridDefinitionDialog

        index = self.custom_grid_list.currentRow()
        if index < 0 or index >= len(self.custom_grid_definitions):
            self.log("No custom grid file selected to edit.")
            return

        vector_layers = self._get_project_vector_layers()
        if not vector_layers:
            self.log("No vector layers found for custom grid definition.")
            return

        dialog = CustomGridDefinitionDialog(
            vector_layers, definition=self.custom_grid_definitions[index], parent=self
        )
        if dialog.exec_() == dialog.Accepted:
            self.custom_grid_definitions[index] = dialog.get_definition()
            self._refresh_custom_grid_list()
            self.log(f"Updated custom grid file "
                     f"'{self.custom_grid_definitions[index].sanitized_filename()}'.")

    def duplicate_custom_grid(self):
        """Duplicate the selected custom grid definition."""
        index = self.custom_grid_list.currentRow()
        if index < 0 or index >= len(self.custom_grid_definitions):
            self.log("No custom grid file selected to duplicate.")
            return

        duplicate = self.custom_grid_definitions[index].copy()
        self.custom_grid_definitions.append(duplicate)
        self._refresh_custom_grid_list()
        self.log(f"Duplicated custom grid file '{duplicate.sanitized_filename()}'. "
                 "Edit the copy to change its filename and values.")

    def remove_custom_grid(self):
        """Remove the selected custom grid definition."""
        index = self.custom_grid_list.currentRow()
        if index < 0 or index >= len(self.custom_grid_definitions):
            self.log("No custom grid file selected to remove.")
            return

        removed = self.custom_grid_definitions.pop(index)
        self._refresh_custom_grid_list()
        self.log(f"Removed custom grid file '{removed.sanitized_filename()}'.")

    def _refresh_custom_grid_list(self):
        """Rebuild the list widget from the current definitions."""
        previous_row = self.custom_grid_list.currentRow()
        self.custom_grid_list.blockSignals(True)
        self.custom_grid_list.clear()
        for definition in self.custom_grid_definitions:
            layer_count = len(definition.layer_values)
            item = QListWidgetItem(
                f"{definition.sanitized_filename()}  "
                f"({layer_count} layer{'s' if layer_count != 1 else ''}, "
                f"default {definition.default_value:g})"
            )
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if definition.enabled else Qt.Unchecked)
            item.setData(Qt.UserRole, definition)
            self.custom_grid_list.addItem(item)
        if self.custom_grid_list.count() > 0:
            self.custom_grid_list.setCurrentRow(
                min(max(previous_row, 0), self.custom_grid_list.count() - 1)
            )
        self.custom_grid_list.blockSignals(False)

    def _on_custom_grid_item_changed(self, item):
        """Sync a definition's enabled flag with its item checkbox."""
        definition = item.data(Qt.UserRole)
        if definition is not None:
            definition.enabled = item.checkState() == Qt.Checked

    def _on_layers_removed(self, layer_ids):
        """Drop layers being removed from the project from all definitions."""
        # The signal has two overloads (layer ids or layer objects); accept both.
        removed = set()
        for entry in layer_ids:
            if isinstance(entry, str):
                removed.add(entry)
            else:
                try:
                    removed.add(entry.id())
                except (RuntimeError, AttributeError):
                    pass
        changed = False
        for definition in self.custom_grid_definitions:
            for layer in list(definition.layer_values.keys()):
                try:
                    layer_gone = layer.id() in removed
                except RuntimeError:
                    layer_gone = True  # Underlying C++ object already deleted.
                if layer_gone:
                    del definition.layer_values[layer]
                    changed = True
        if changed:
            self._refresh_custom_grid_list()
            self.log("Custom grid files updated: removed project layers were dropped.")

    def select_threshold_layers(self):
        """Select threshold mask layers and assign complex values."""
        from SCOPE.gui.threshold_mask_selection import ThresholdMaskSelectionDialog

        vector_layers = self._get_project_vector_layers()

        if not vector_layers:
            self.log("No vector layers found for threshold mask selection.")
            return

        threshold_dialog = ThresholdMaskSelectionDialog(vector_layers, default_real=1.0, default_imag=0.0)
        if threshold_dialog.exec_() == threshold_dialog.Accepted:
            self.selected_threshold_layers = threshold_dialog.get_selected_layers()
            self.threshold_default_value = threshold_dialog.get_default_value()
            if self.selected_threshold_layers:
                layer_names = [layer.name() for layer in self.selected_threshold_layers.keys()]
                self.log(f"Selected threshold mask layers: {', '.join(layer_names)}")
                for layer, complex_val in self.selected_threshold_layers.items():
                    self.log(f"  {layer.name()}: {complex_val.real:.3f}+{complex_val.imag:.3f}j")
                self.log(f"Default value for non-masked areas: {self.threshold_default_value.real:.3f}+{self.threshold_default_value.imag:.3f}j")
                self.select_threshold_btn.setText(f"Threshold: {len(self.selected_threshold_layers)} layers")
            else:
                self.log("No threshold mask layers selected.")
                self.select_threshold_btn.setText("Threshold mask")

    def _update_process_button_state(self):
        """Enable/disable process button based on selections."""
        has_bathymetry = len(self.selected_bathymetry_layers) > 0 or self.selected_bathymetry is not None
        has_geometry = self.current_geometry is not None
        self.process_btn.setEnabled(has_bathymetry and has_geometry)

    def start_rectangle_tool(self):
        """Start the model area drawing tool."""
        width = self.width_spin.value()
        height = self.height_spin.value()
        angle = self.rotation_spin.value()
        anchor_mode = self.anchor_combo.currentText()

        self.rect_tool = RectTool(iface.mapCanvas(), self)
        self.rect_tool.set_dimensions(width, height, angle, anchor_mode)
        self.rect_tool.rectangleDrawn.connect(self.on_rectangle_drawn)
        iface.mapCanvas().setMapTool(self.rect_tool)

        if anchor_mode == "Center":
            self.log(f"Click on the map to place the center of a {width}m x {height}m model area (angle: {angle}°)...")
        else:  # XBeach coordinate origin
            self.log(f"Click on the map to place the origin (bottom-left) of a {width}m x {height}m model area (angle: {angle}°)...")

    def on_rectangle_drawn(self, geometry, ll_point, centre_point):
        """Called when model area is drawn on map."""
        self.clear_existing_model_areas()

        self.current_geometry = geometry
        self.ll_point = ll_point
        self.centre_point = centre_point

        # Reset split areas when new model area is drawn
        self.split_areas = []
        self.split_rows = 1
        self.split_cols = 1

        if self.rect_tool:
            iface.mapCanvas().unsetMapTool(self.rect_tool)

        self._update_process_button_state()
        self.split_area_btn.setEnabled(True)  # Enable split button
        self.move_area_btn.setEnabled(True)
        self.log("Model area drawn. Ready to process or split into sub-areas.")

    def show_welcome_screen(self):
        """Re-show the welcome screen and re-enable it for future launches."""
        from SCOPE.gui.welcome_dialog import WelcomeDialog
        WelcomeDialog.reset_preference()
        WelcomeDialog(self).exec_()

    def toggle_move_tool(self):
        """Toggle the move tool on/off via the Move model area button."""
        if self.move_tool is not None:
            self.stop_move_tool()
        else:
            self.start_move_tool()

    def start_move_tool(self):
        """Activate tool to drag the current model area to a new position."""
        if not self.current_geometry or not self.ll_point or not self.centre_point:
            QMessageBox.warning(self, "No model area", "Please draw a model area first.")
            return

        self.move_tool = MoveModelAreaTool(
            iface.mapCanvas(),
            self.current_geometry,
            self.ll_point,
            self.centre_point,
            self,
        )
        self.move_tool.areaMoved.connect(self.on_model_area_moved)
        # Reset the button if QGIS deactivates the tool externally (e.g. the
        # user switches to another map tool such as "Draw Model Area").
        self.move_tool.deactivated.connect(self._on_move_tool_deactivated)
        iface.mapCanvas().setMapTool(self.move_tool)
        self._set_move_button_active(True)
        self.log("Move mode enabled. Drag the red model area to the desired position.")

    def stop_move_tool(self):
        """Deactivate the move tool so the model area can no longer be dragged."""
        if self.move_tool is not None:
            # Triggers _on_move_tool_deactivated, which clears state and button.
            iface.mapCanvas().unsetMapTool(self.move_tool)
        self.log("Move mode disabled.")

    def _on_move_tool_deactivated(self):
        """Clear move-tool state when the tool is deactivated (by us or QGIS)."""
        self.move_tool = None
        self._set_move_button_active(False)

    def _set_move_button_active(self, active):
        """Update the Move model area button label/style to reflect move mode."""
        if active:
            self.move_area_btn.setText("Stop moving")
            self.move_area_btn.setStyleSheet(
                "background-color: #f5b5b5;"
            )
        else:
            self.move_area_btn.setText("Move model area")
            self.move_area_btn.setStyleSheet("")

    def on_model_area_moved(self, geometry, ll_point, centre_point):
        """Update dialog state after model area has been moved."""
        self.current_geometry = geometry
        self.ll_point = ll_point
        self.centre_point = centre_point

        # Keep XBeach axes/origin visualization synchronized with moved box.
        if self.anchor_combo.currentText() == "XBeach coordinate origin":
            from SCOPE.utils.geometry import update_axes_visualization
            update_axes_visualization(
                ll_point,
                self.width_spin.value(),
                self.height_spin.value(),
                self.rotation_spin.value(),
                True,
            )

        # Moving invalidates previous split configuration.
        self.split_areas = []
        self.split_rows = 1
        self.split_cols = 1
        self.split_area_btn.setEnabled(True)
        self.move_area_btn.setEnabled(True)
        self._update_process_button_state()
        self.log("Model area moved. Split areas reset; re-split if needed.")

    def clear_existing_model_areas(self):
        """Clear any existing model area layers from the map."""
        try:
            from qgis.core import QgsProject
            project = QgsProject.instance()

            layers_to_remove = []
            for layer in project.mapLayers().values():
                if layer.name() in ["Model area", "Model center", "Split areas"]:
                    layers_to_remove.append(layer.id())

            for layer_id in layers_to_remove:
                project.removeMapLayer(layer_id)

        except Exception as e:
            self.log(f"Warning: Could not clear existing model areas: {e}")

    def _remove_input_layers(self):
        """Remove drawing/input layers after processing.

        Leaves only the result layers (the "Processed model area" subgroup and,
        for split runs, the "Split areas" layer).
        """
        try:
            from qgis.core import QgsProject
            project = QgsProject.instance()
            for name in ("Model area", "Model center"):
                for layer in list(project.mapLayersByName(name)):
                    project.removeMapLayer(layer.id())
            from SCOPE.utils.geometry import clear_xbeach_layers
            clear_xbeach_layers()
        except Exception as e:
            self.log(f"Warning: Could not remove input layers: {e}")

    def split_model_area(self):
        """Open dialog to split the current model area into sub-areas."""
        if not self.current_geometry:
            QMessageBox.warning(self, "No model area", "Please draw a model area first.")
            return

        dialog = SplitAreaDialog(self.split_rows, self.split_cols)
        if dialog.exec_() == dialog.Accepted:
            self.split_rows, self.split_cols = dialog.get_split_configuration()
            self.create_split_areas()
            self.log(f"Model area split into {self.split_rows}×{self.split_cols} sub-areas.")

    def create_split_areas(self):
        """Create sub-areas by splitting the current model area."""
        if not self.current_geometry:
            return

        bbox = self.current_geometry.boundingBox()

        total_width = bbox.width()
        total_height = bbox.height()
        sub_width = total_width / self.split_cols
        sub_height = total_height / self.split_rows

        self.split_areas = []

        for row in range(self.split_rows):
            for col in range(self.split_cols):
                min_x = bbox.xMinimum() + col * sub_width
                max_x = min_x + sub_width
                min_y = bbox.yMinimum() + row * sub_height
                max_y = min_y + sub_height

                from qgis.core import QgsGeometry, QgsPointXY
                corners = [
                    QgsPointXY(min_x, min_y),
                    QgsPointXY(max_x, min_y),
                    QgsPointXY(max_x, max_y),
                    QgsPointXY(min_x, max_y),
                    QgsPointXY(min_x, min_y)  # Close the polygon
                ]

                sub_area_geom = QgsGeometry.fromPolygonXY([corners])

                area_info = {
                    'geometry': sub_area_geom,
                    'row': row + 1,  # 1-based indexing
                    'col': col + 1,  # 1-based indexing
                    'name': f"area_row{row + 1}_col{col + 1}",
                    'll_point': QgsPointXY(min_x, min_y),
                    'center_point': QgsPointXY(min_x + sub_width/2, min_y + sub_height/2)
                }

                self.split_areas.append(area_info)

        self.create_split_areas_layer()

    def create_split_areas_layer(self):
        """Create a visualization layer for the split areas."""
        try:
            from qgis.core import (
                QgsVectorLayer, QgsFeature, QgsProject, QgsField,
                QgsFillSymbol
            )
            from qgis.PyQt.QtCore import QVariant
            from qgis.PyQt.QtGui import QColor
            from SCOPE.utils.layer_utils import add_layer_to_group

            project = QgsProject.instance()
            existing_layers = project.mapLayersByName("Split areas")
            for layer in existing_layers:
                project.removeMapLayer(layer.id())

            split_layer = QgsVectorLayer(f"Polygon?crs={get_working_crs().authid()}", "Split areas", "memory")
            if not split_layer.isValid():
                self.log("Error: Could not create split areas layer")
                return

            split_layer.dataProvider().addAttributes([
                QgsField("area_name", QVariant.String),
                QgsField("row", QVariant.Int),
                QgsField("col", QVariant.Int)
            ])
            split_layer.updateFields()

            features = []
            for area_info in self.split_areas:
                feature = QgsFeature()
                feature.setGeometry(area_info['geometry'])
                feature.setAttributes([
                    area_info['name'],
                    area_info['row'],
                    area_info['col']
                ])
                features.append(feature)

            split_layer.dataProvider().addFeatures(features)
            split_layer.updateExtents()

            symbol = QgsFillSymbol.createSimple({
                'color': '255,255,0,60',  # Semi-transparent yellow
                'outline_color': '255,0,0,255',  # Red border
                'outline_width': '0.8',
                'style': 'solid'
            })
            split_layer.renderer().setSymbol(symbol)

            # Add labels showing row,col numbers
            from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat, QgsTextBufferSettings
            from qgis.PyQt.QtGui import QFont

            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "row || ',' || col"  # Expression to show "row,col"
            label_settings.enabled = True
            # Use centroid for label placement (most reliable for polygons)
            label_settings.centroidWhole = True
            label_settings.centroidInside = True

            text_format = QgsTextFormat()
            font = QFont("Arial", 12, QFont.Bold)
            text_format.setFont(font)
            text_format.setSize(12)
            text_format.setColor(QColor(0, 0, 0))  # Black text

            # Add white buffer for better visibility
            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(1.5)
            buffer_settings.setColor(QColor(255, 255, 255))  # White buffer
            text_format.setBuffer(buffer_settings)

            label_settings.setFormat(text_format)

            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            split_layer.setLabelsEnabled(True)
            split_layer.setLabeling(labeling)

            add_layer_to_group(split_layer)
            self.log("Split areas visualization with row,col labels added to SCOPE group")

            iface.mapCanvas().refresh()

        except Exception as e:
            self.log(f"Error creating split areas visualization: {e}")
            import traceback
            traceback.print_exc()

    RESERVED_GRID_FILENAMES = {"x.grd", "y.grd", "z.grd", "threshold_mask.grd"}

    def _validate_custom_grid_definitions(self):
        """Check the enabled custom grid definitions; warn and return False on problems."""
        seen = set()
        for definition in (d for d in self.custom_grid_definitions if d.enabled):
            name = definition.sanitized_filename()
            if not name:
                QMessageBox.warning(self, "Custom grid files",
                                    "A custom grid file has no filename. "
                                    "Please edit it or remove it.")
                return False
            if "/" in definition.filename or "\\" in definition.filename:
                QMessageBox.warning(self, "Custom grid files",
                                    f"'{definition.filename}' contains path separators. "
                                    "Please use a plain filename.")
                return False
            if name.lower() in self.RESERVED_GRID_FILENAMES:
                QMessageBox.warning(self, "Custom grid files",
                                    f"'{name}' is reserved for SCOPE's standard outputs. "
                                    "Please choose another filename.")
                return False
            if name in seen:
                QMessageBox.warning(self, "Custom grid files",
                                    f"Two enabled custom grids share the filename '{name}'. "
                                    "Please rename or disable one of them.")
                return False
            if not definition.valid_layer_values():
                QMessageBox.warning(self, "Custom grid files",
                                    f"Custom grid '{name}' has no polygon layers selected "
                                    "(or its layers were removed from the project). "
                                    "Please edit, disable or remove it.")
                return False
            seen.add(name)
        return True

    def process_area(self):
        """Process the selected area with current settings."""
        if not self.current_geometry:
            QMessageBox.warning(self, "No model area", "Please draw a model area first.")
            return

        if not (self.selected_bathymetry_layers or self.selected_bathymetry):
            QMessageBox.warning(self, "No bathymetry", "Please select bathymetry data first.")
            return

        if not self._validate_custom_grid_definitions():
            return


        # Apply the chosen working CRS for this run (defaults to project CRS).
        selected_crs = self.crs_widget.crs()
        if selected_crs.isValid():
            set_working_crs(selected_crs)
            self.log(f"Working CRS: {selected_crs.authid() or selected_crs.description()}")
        else:
            set_working_crs(None)
            self.log("Working CRS: project CRS (no valid CRS selected).")

        if self.split_areas:
            self.process_split_areas()
        else:
            self.process_single_area()

    def process_single_area(self):
        """Process a single model area."""
        rasters = self.selected_bathymetry_layers or ([self.selected_bathymetry] if self.selected_bathymetry else [])
        if not rasters:
            QMessageBox.warning(self, "No bathymetry", "Please select at least one bathymetry raster first.")
            return

        batch_mode = len(rasters) > 1
        batch_output_dir = None
        batch_log_path = None
        single_xyz_path = None

        if not batch_mode:
            raster_name = rasters[0].name()
            xyz_file, _ = QFileDialog.getSaveFileName(
                self, f"Save XYZ for {raster_name}", f"{raster_name}_clipped.xyz",
                "XYZ (*.xyz);;All files (*.*)"
            )
            if not xyz_file:
                self.log(f"XYZ save cancelled for {raster_name}")
                return
            if not xyz_file.lower().endswith(".xyz"):
                xyz_file += ".xyz"
            single_xyz_path = Path(xyz_file)
        else:
            batch_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Output Directory for Batch Processing",
                "",
            )
            if not batch_dir:
                self.log("Batch processing cancelled: no output directory selected.")
                return

            batch_output_dir = batch_dir
            batch_log_path = str((Path(batch_dir) / "batch_processing.log"))
            with open(batch_log_path, "a", encoding="utf-8") as lf:
                lf.write("\n" + "=" * 80 + "\n")
                lf.write("SCOPE batch started\n")
                lf.write(f"Rasters: {len(rasters)}\n")
                lf.write("=" * 80 + "\n")
            self.log(f"Batch output directory: {batch_output_dir}")
            self.log(f"Batch log file: {batch_log_path}")

        self.progress.setVisible(True)
        self.progress.setRange(0, len(rasters))

        try:
            for i, raster in enumerate(rasters):
                self.progress.setValue(i)
                self.log(f"Processing bathymetry {i+1}/{len(rasters)}: {raster.name()}")

                if batch_mode:
                    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raster.name())
                    xyz_path = Path(batch_output_dir) / safe_name / f"{safe_name}_clipped.xyz"
                    log_path = batch_log_path
                else:
                    xyz_path = single_xyz_path
                    log_path = xyz_path.parent / "processing.log"

                self.process_single_raster(
                    raster,
                    self.current_geometry,
                    self.ll_point,
                    self.centre_point,
                    self.width_spin.value(),
                    self.height_spin.value(),
                    self.rotation_spin.value(),
                    xyz_path=xyz_path,
                    log_path=log_path,
                )

            self.progress.setValue(len(rasters))
            self._remove_input_layers()
            self.log("Processing completed!")

        except Exception as e:
            self.log(f"Error during processing: {str(e)}")
            QMessageBox.critical(self, "Processing Error", f"Error: {str(e)}")
        finally:
            self.progress.setVisible(False)

    def process_split_areas(self):
        """Process multiple split areas."""
        rasters = self.selected_bathymetry_layers or ([self.selected_bathymetry] if self.selected_bathymetry else [])
        if not rasters:
            QMessageBox.warning(self, "No bathymetry", "Please select at least one bathymetry raster first.")
            return

        base_dir = QFileDialog.getExistingDirectory(self, "Select Base Directory for Split Areas", "")
        if not base_dir:
            self.log("Split processing cancelled: no base directory selected.")
            return
        base_dir = Path(base_dir)
        log_path = base_dir / "split_processing.log"
        self.log(f"Base directory selected: {base_dir}")

        total_areas = len(self.split_areas) * len(rasters)
        self.progress.setVisible(True)
        self.progress.setRange(0, total_areas)

        try:
            self.log(f"Processing {len(self.split_areas)} sub-areas for {len(rasters)} raster(s)...")
            self.log("A subdirectory is created for each sub-area.")

            step = 0
            for raster in rasters:
                for area_info in self.split_areas:
                    self.progress.setValue(step)
                    self.log(f"Processing {raster.name()} / {area_info['name']} ({step+1}/{total_areas})")

                    output_prefix = f"{raster.name()}_{area_info['name']}"
                    bbox = area_info['geometry'].boundingBox()
                    sub_width = bbox.width()
                    sub_height = bbox.height()

                    self.process_single_raster(
                        raster,
                        area_info['geometry'],
                        area_info['ll_point'],
                        area_info['center_point'],
                        sub_width,
                        sub_height,
                        self.rotation_spin.value(),
                        output_prefix=output_prefix,
                        xyz_path=base_dir / output_prefix / f"{raster.name()}_clipped.xyz",
                        log_path=log_path,
                    )
                    step += 1

            self.progress.setValue(total_areas)
            self._remove_input_layers()
            self.log(f"All {total_areas} sub-areas processed successfully!")

        except Exception as e:
            self.log(f"Error during split area processing: {str(e)}")
            QMessageBox.critical(self, "Processing Error", f"Error: {str(e)}")
        finally:
            self.progress.setVisible(False)

    def process_single_raster(
        self,
        raster,
        rect_geom,
        ll,
        centre,
        w,
        h,
        ang_deg,
        output_prefix=None,
        xyz_path=None,
        log_path=None,
    ):
        """Process a single raster with the given model area."""
        coord_system = "local" if self.coord_combo.currentIndex() == 0 else "world"

        # Check if adaptive grid is enabled (configured via AdaptiveGridDialog)
        use_adaptive = self.adaptive_dialog.is_enabled() and self.create_grids_cb.isChecked()

        min_cell_size = None
        max_cell_size = None
        adaptive_z_threshold = None
        longshore_cell_size = self.dy_spin.value()

        if use_adaptive:
            min_cell_size = self.adaptive_dialog.min_cell_size_spin.value()
            max_cell_size = self.adaptive_dialog.max_cell_size_spin.value()
            adaptive_z_threshold = self.adaptive_dialog.adaptive_threshold_spin.value()
            longshore_cell_size = self.adaptive_dialog.adaptive_longshore_size_spin.value()

            if max_cell_size <= min_cell_size:
                self.log("Warning: Max Δx must be greater than Min Δx. Using uniform grid.")
                use_adaptive = False
            else:
                self.log(
                    f"Creating threshold-based adaptive grid: {max_cell_size}m (offshore) to {min_cell_size}m (onshore), fine zone where bed level > {adaptive_z_threshold}m, longshore Δy={longshore_cell_size}m"
                )

        anchor_mode = self.anchor_combo.currentText()
        clip_translate_grid_gui(
            raster, rect_geom, ll, centre, w, h, ang_deg,
            self.dx_spin.value(), longshore_cell_size if use_adaptive else self.dy_spin.value(),
            self.create_grids_cb.isChecked(),
            self.log,
            coord_system=coord_system,
            use_adaptive_grid=use_adaptive,
            min_cell_size=min_cell_size if use_adaptive else None,
            max_cell_size=max_cell_size if use_adaptive else None,
            anchor_mode=anchor_mode,
            custom_grid_definitions=[d for d in self.custom_grid_definitions if d.enabled],
            threshold_layers=self.selected_threshold_layers,
            threshold_default_value=self.threshold_default_value,
            output_prefix=output_prefix,
            create_visualization=output_prefix is None,  # Only create visualization for single areas
            adaptive_z_threshold=adaptive_z_threshold if use_adaptive else None,
            adaptive_transition_factor=None,
            show_grid_spacing_preview=self.preview_spacing_cb.isChecked() and output_prefix is None,
            show_bed_2d_preview=self.preview_bed2d_cb.isChecked() and output_prefix is None,
            show_bed_3d_preview=self.preview_bed3d_cb.isChecked() and output_prefix is None,
            show_custom_grid_preview=self.preview_custom_cb.isChecked() and output_prefix is None,
            xyz_path=xyz_path,
            log_path=log_path,
        )

    def on_anchor_point_changed(self, text):
        """Handle anchor point selection changes."""
        if text != "XBeach coordinate origin":
            from SCOPE.utils.geometry import clear_xbeach_layers
            clear_xbeach_layers()
            self.log("Switched to Center mode. XBeach visualization layers cleared.")
        else:
            self.log("Switched to XBeach coordinate origin mode. Click on map to place origin and visualize axes.")

    def initialize_layer_visibility(self):
        """Initialize XBeach layer visibility based on current anchor mode."""
        if self.anchor_combo.currentText() != "XBeach coordinate origin":
            from SCOPE.utils.geometry import clear_xbeach_layers
            clear_xbeach_layers()


class SplitAreaDialog(QDialog):
    """Dialog for configuring model area splitting."""

    def __init__(self, current_rows=1, current_cols=1):
        super().__init__()
        self.setWindowTitle("Split model area")
        self.setMinimumSize(300, 200)
        self.current_rows = current_rows
        self.current_cols = current_cols
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Split model area configuration")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        instructions = QLabel(
            "Specify how to split the model area into sub-areas.\n"
            "Each sub-area will be processed separately with the same settings."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("margin: 10px; padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(instructions)

        config_group = QGroupBox("Split Configuration")
        config_layout = QFormLayout(config_group)

        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 10)
        self.rows_spin.setValue(self.current_rows)
        self.rows_spin.setToolTip("Number of rows (vertical divisions)")
        config_layout.addRow("Rows:", self.rows_spin)

        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 10)
        self.cols_spin.setValue(self.current_cols)
        self.cols_spin.setToolTip("Number of columns (horizontal divisions)")
        config_layout.addRow("Columns:", self.cols_spin)

        self.total_label = QLabel()
        self.update_total_label()
        config_layout.addRow("Total Sub-areas:", self.total_label)

        self.rows_spin.valueChanged.connect(self.update_total_label)
        self.cols_spin.valueChanged.connect(self.update_total_label)

        layout.addWidget(config_group)

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def update_total_label(self):
        """Update the total sub-areas label."""
        total = self.rows_spin.value() * self.cols_spin.value()
        self.total_label.setText(f"{total} sub-areas")

    def get_split_configuration(self):
        """Return the split configuration as (rows, cols)."""
        return self.rows_spin.value(), self.cols_spin.value()
