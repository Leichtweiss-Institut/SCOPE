"""
Dialog for selecting raster layers.
"""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QMessageBox
)
from qgis.core import QgsProject


def select_raster_layers():
    """
    Select one or more raster layers from the project.

    Returns:
        list: Selected raster layers
    """
    project = QgsProject.instance()
    raster_layers = []

    for layer in project.mapLayers().values():
        if hasattr(layer, 'type') and layer.type() == layer.RasterLayer:
            raster_layers.append(layer)

    if not raster_layers:
        QMessageBox.warning(None, "No Rasters", "No raster layers found in the project.")
        return []

    dialog = QDialog()
    dialog.setWindowTitle("Select Raster Layer(s)")
    dialog.setMinimumSize(400, 300)
    layout = QVBoxLayout(dialog)

    label = QLabel("Select one or more raster layers to process:")
    layout.addWidget(label)

    list_widget = QListWidget()
    for layer in raster_layers:
        item = QListWidgetItem(layer.name())
        item.setData(Qt.UserRole, layer)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        list_widget.addItem(item)
    layout.addWidget(list_widget)

    buttons = QHBoxLayout()
    ok_btn = QPushButton("OK")
    cancel_btn = QPushButton("Cancel")
    buttons.addWidget(ok_btn)
    buttons.addWidget(cancel_btn)
    layout.addLayout(buttons)

    ok_btn.clicked.connect(dialog.accept)
    cancel_btn.clicked.connect(dialog.reject)

    if dialog.exec_() == QDialog.Accepted:
        selected = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected
    return []
