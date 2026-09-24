"""
Map tools for SCOPE.
"""
from qgis.core import Qgis, QgsGeometry, QgsMessageLog, QgsPointXY, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor

from ..utils.constants import get_working_crs


def _create_model_area_layers(canvas, geometry, center_point):
    """Create or refresh persistent model area layers."""
    try:
        from qgis.core import (
            QgsVectorLayer,
            QgsFeature,
            QgsProject,
            QgsFillSymbol,
            QgsMarkerSymbol,
            QgsGeometry,
        )
        from ..utils.layer_utils import add_layer_to_group

        existing_layers = QgsProject.instance().mapLayersByName("Model area")
        for layer in existing_layers:
            QgsProject.instance().removeMapLayer(layer.id())

        existing_centers = QgsProject.instance().mapLayersByName("Model center")
        for layer in existing_centers:
            QgsProject.instance().removeMapLayer(layer.id())

        rect_layer = QgsVectorLayer(f"Polygon?crs={get_working_crs().authid()}", "Model area", "memory")
        if rect_layer.isValid():
            feature = QgsFeature()
            feature.setGeometry(geometry)
            rect_layer.dataProvider().addFeatures([feature])
            rect_layer.updateExtents()
            # Viridis teal (#21918c) outline/fill — colour-blind friendly.
            symbol = QgsFillSymbol.createSimple(
                {
                    "color": "33,145,140,50",
                    "outline_color": "33,145,140,255",
                    "outline_width": "0.5",
                    "style": "solid",
                }
            )
            rect_layer.renderer().setSymbol(symbol)
            add_layer_to_group(rect_layer)

        center_layer = QgsVectorLayer(f"Point?crs={get_working_crs().authid()}", "Model center", "memory")
        if center_layer.isValid():
            center_feature = QgsFeature()
            center_feature.setGeometry(QgsGeometry.fromPointXY(center_point))
            center_layer.dataProvider().addFeatures([center_feature])
            center_layer.updateExtents()
            marker_symbol = QgsMarkerSymbol.createSimple(
                {
                    "name": "cross",
                    "color": "0,0,0,255",
                    "size": "4",
                    "outline_color": "0,0,0,255",
                }
            )
            center_layer.renderer().setSymbol(marker_symbol)
            add_layer_to_group(center_layer)

        canvas.refresh()
    except Exception as e:
        QgsMessageLog.logMessage(f"Error creating model area layers: {e}", "SCOPE", Qgis.Warning)


class RectTool(QgsMapTool):
    """Map tool for creating rectangles with specified dimensions."""

    rectangleDrawn = pyqtSignal(object, object, object)  # geometry, ll_point, center_point

    def __init__(self, canvas, parent=None):
        """Initialize the rectangle tool."""
        super().__init__(canvas)
        self.canvas = canvas
        self.parent = parent

        self.rect_rubber_band = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.rect_rubber_band.setColor(QColor(255, 0, 0, 200))  # Red border
        self.rect_rubber_band.setFillColor(QColor(255, 0, 0, 30))  # Light red fill
        self.rect_rubber_band.setWidth(2)

        self.cross_rubber_band = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.cross_rubber_band.setColor(QColor(0, 0, 0, 255))  # Black cross
        self.cross_rubber_band.setWidth(2)

        # Defaults; the dialog sets the actual values.
        self.width = 1000  # meters
        self.height = 1000  # meters
        self.angle = 0  # degrees
        self.anchor_mode = "Center"  # Default anchor mode

    def set_dimensions(self, width, height, angle=0, anchor_mode="Center"):
        """Set the rectangle dimensions and anchor mode."""
        self.width = width
        self.height = height
        self.angle = angle
        self.anchor_mode = anchor_mode

    def activate(self):
        """Activate the tool."""
        super().activate()
        self.canvas.setCursor(Qt.CrossCursor)

    def deactivate(self):
        """Deactivate the tool."""
        self.rect_rubber_band.reset()
        self.cross_rubber_band.reset()
        if hasattr(self, 'vertical_cross'):
            self.vertical_cross.reset()
        super().deactivate()

    def canvasPressEvent(self, event):
        """Handle mouse press events - create rectangle at click point."""
        if event.button() == Qt.LeftButton:
            click_point = self.toMapCoordinates(event.pos())
            self.create_rectangle_at_point(click_point)

    def create_rectangle_at_point(self, click_point):
        """Create a rectangle with specified dimensions at the given click point."""
        self.rect_rubber_band.reset()
        self.cross_rubber_band.reset()

        if hasattr(self, 'vertical_cross'):
            self.vertical_cross.reset()

        if self.anchor_mode == "Center":
            center_point = click_point
            ll_point = QgsPointXY(center_point.x() - self.width / 2, center_point.y() - self.height / 2)
            rotation_center = center_point
        else:  # XBeach coordinate origin
            ll_point = click_point
            center_point = QgsPointXY(ll_point.x() + self.width / 2, ll_point.y() + self.height / 2)
            rotation_center = click_point  # Rotate around the origin

        corners = [
            ll_point,  # bottom-left
            QgsPointXY(ll_point.x() + self.width, ll_point.y()),  # bottom-right
            QgsPointXY(ll_point.x() + self.width, ll_point.y() + self.height),  # top-right
            QgsPointXY(ll_point.x(), ll_point.y() + self.height),  # top-left
            ll_point  # close polygon
        ]

        if self.angle != 0:
            corners = self.rotate_points(corners, rotation_center, self.angle)
            # Keep center marker consistent with rotated geometry in XBeach origin mode.
            if self.anchor_mode == "XBeach coordinate origin":
                center_point = self.rotate_points([center_point], rotation_center, self.angle)[0]

        for corner in corners:
            self.rect_rubber_band.addPoint(corner)

        if self.anchor_mode == "Center":
            cross_center = center_point
        else:  # XBeach coordinate origin
            cross_center = click_point

        cross_size = min(self.width, self.height) * 0.1  # 10% of smaller dimension

        self.cross_rubber_band.addPoint(QgsPointXY(cross_center.x() - cross_size, cross_center.y()))
        self.cross_rubber_band.addPoint(QgsPointXY(cross_center.x() + cross_size, cross_center.y()))

        vertical_cross = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        vertical_cross.setColor(QColor(0, 0, 0, 255))
        vertical_cross.setWidth(2)
        vertical_cross.addPoint(QgsPointXY(cross_center.x(), cross_center.y() - cross_size))
        vertical_cross.addPoint(QgsPointXY(cross_center.x(), cross_center.y() + cross_size))

        self.vertical_cross = vertical_cross

        rect_geom = QgsGeometry.fromPolygonXY([corners[:-1]])  # Remove duplicate closing point

        self.canvas.refresh()

        self.rectangleDrawn.emit(rect_geom, ll_point, center_point)

        self.create_model_area_layer(rect_geom, center_point)

        if self.anchor_mode == "XBeach coordinate origin":
            self.show_xbeach_axes(click_point, self.width, self.height, self.angle)
        else:
            self.clear_xbeach_axes()

    def rotate_points(self, points, center, angle_degrees):
        """Rotate points around center by given angle."""
        import math
        angle_rad = math.radians(angle_degrees)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        rotated = []
        for point in points:
            x = point.x() - center.x()
            y = point.y() - center.y()

            x_rot = x * cos_a - y * sin_a
            y_rot = x * sin_a + y * cos_a

            rotated.append(QgsPointXY(center.x() + x_rot, center.y() + y_rot))

        return rotated

    def reset_rectangle(self):
        """Reset/clear the current rectangle."""
        self.rect_rubber_band.reset()
        self.cross_rubber_band.reset()
        if hasattr(self, 'vertical_cross'):
            self.vertical_cross.reset()

    def create_model_area_layer(self, geometry, center_point):
        """Create a persistent vector layer for the model area."""
        _create_model_area_layers(self.canvas, geometry, center_point)

    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key_Escape:
            self.reset_rectangle()

    def show_xbeach_axes(self, origin_point, width, height, angle):
        """Show XBeach coordinate axes from the origin point."""
        try:
            from ..utils.geometry import update_axes_visualization
            update_axes_visualization(origin_point, width, height, angle, is_xbeach_origin=True)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error showing XBeach axes: {e}", "SCOPE", Qgis.Warning)

    def clear_xbeach_axes(self):
        """Clear XBeach axes visualization."""
        try:
            from ..utils.geometry import clear_xbeach_layers
            clear_xbeach_layers()
        except Exception as e:
            QgsMessageLog.logMessage(f"Error clearing XBeach axes: {e}", "SCOPE", Qgis.Warning)


class MoveModelAreaTool(QgsMapTool):
    """Map tool for dragging the existing model area polygon."""

    areaMoved = pyqtSignal(object, object, object)  # geometry, ll_point, center_point

    def __init__(self, canvas, geometry, ll_point, center_point, parent=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.parent = parent
        self.base_geometry = QgsGeometry(geometry)
        self.base_ll = QgsPointXY(ll_point)
        self.base_center = QgsPointXY(center_point)
        self.dragging = False
        self.start_point = None
        self.current_dx = 0.0
        self.current_dy = 0.0

        self.preview_band = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.preview_band.setColor(QColor(255, 0, 0, 220))
        self.preview_band.setFillColor(QColor(255, 0, 0, 40))
        self.preview_band.setWidth(2)

    def activate(self):
        super().activate()
        self.canvas.setCursor(Qt.OpenHandCursor)
        self._update_preview(self.base_geometry)

    def deactivate(self):
        self.preview_band.reset()
        super().deactivate()

    def canvasPressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        point = self.toMapCoordinates(event.pos())
        point_geom = QgsGeometry.fromPointXY(point)
        if self.base_geometry.contains(point_geom):
            self.dragging = True
            self.start_point = point
            self.current_dx = 0.0
            self.current_dy = 0.0
            self.canvas.setCursor(Qt.ClosedHandCursor)

    def canvasMoveEvent(self, event):
        if not self.dragging or self.start_point is None:
            return

        point = self.toMapCoordinates(event.pos())
        self.current_dx = point.x() - self.start_point.x()
        self.current_dy = point.y() - self.start_point.y()

        geom = QgsGeometry(self.base_geometry)
        geom.translate(self.current_dx, self.current_dy)
        self._update_preview(geom)

    def canvasReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.dragging:
            return

        self.dragging = False
        self.canvas.setCursor(Qt.OpenHandCursor)

        geom = QgsGeometry(self.base_geometry)
        geom.translate(self.current_dx, self.current_dy)

        new_ll = QgsPointXY(self.base_ll.x() + self.current_dx, self.base_ll.y() + self.current_dy)
        new_center = QgsPointXY(self.base_center.x() + self.current_dx, self.base_center.y() + self.current_dy)

        self.base_geometry = QgsGeometry(geom)
        self.base_ll = QgsPointXY(new_ll)
        self.base_center = QgsPointXY(new_center)

        _create_model_area_layers(self.canvas, geom, new_center)
        self.areaMoved.emit(geom, new_ll, new_center)

    def _update_preview(self, geometry):
        self.preview_band.reset()
        if geometry:
            self.preview_band.setToGeometry(geometry, None)
