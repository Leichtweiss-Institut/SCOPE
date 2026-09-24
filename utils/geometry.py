"""
Utility functions for SCOPE.
"""
import math
from qgis.core import (
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsLineString,
    QgsSymbol,
    QgsSingleSymbolRenderer,
    QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

from SCOPE.utils.constants import get_working_crs, AXIS_LAYER_NAME, ORIGIN_POINT_LAYER_NAME
from SCOPE.utils.layer_utils import add_layer_to_group


def reproject_geom(geom, src_crs, dst_crs):
    """
    Reproject a geometry from one CRS to another.

    Args:
        geom: Geometry to reproject
        src_crs: Source CRS
        dst_crs: Destination CRS

    Returns:
        QgsGeometry: Reprojected geometry
    """
    if src_crs == dst_crs:
        return QgsGeometry(geom)
    ct = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
    g2 = QgsGeometry(geom)
    g2.transform(ct)
    return g2


def rot_point(x, y, ang_deg, ox, oy):
    """
    Rotate a point around an origin.

    Args:
        x, y: Point coordinates
        ang_deg: Rotation angle in degrees
        ox, oy: Origin coordinates

    Returns:
        tuple: (x, y) rotated coordinates
    """
    r = math.radians(ang_deg)
    c, s = math.cos(r), math.sin(r)
    return (x - ox) * c - (y - oy) * s + ox, (x - ox) * s + (y - oy) * c + oy


def axis_layer():
    """
    Get or create a temporary axis layer for XBeach origin visualization.

    Returns:
        QgsVectorLayer: The axis layer
    """
    prj = QgsProject.instance()
    lst = prj.mapLayersByName(AXIS_LAYER_NAME)
    if lst:
        return lst[0]
    vl = QgsVectorLayer(f"LineString?crs={get_working_crs().authid()}", AXIS_LAYER_NAME, "memory")
    vl.dataProvider().addAttributes([
        QgsField("id", QVariant.Int),
        QgsField("axis_type", QVariant.String)
    ])
    vl.updateFields()
    add_layer_to_group(vl)
    return vl


def create_axis_lines(origin_point, w, h, ang_deg):
    """
    Create axis lines from the XBeach origin point.

    Args:
        origin_point: Origin point (QgsPointXY)
        w: Width in map units
        h: Height in map units
        ang_deg: Rotation angle in degrees

    Returns:
        list: List of (geometry, axis_type) tuples
    """
    # Calculate axis endpoints (slightly extend beyond rectangle)
    extension_factor = 0.1  # 10% extension beyond rectangle
    x_axis_length = w * (1 + extension_factor)
    y_axis_length = h * (1 + extension_factor)

    ang = math.radians(ang_deg)
    ox, oy = origin_point.x(), origin_point.y()

    # X-axis (red) - pointing right from origin
    x_end_x = ox + x_axis_length * math.cos(ang)
    x_end_y = oy + x_axis_length * math.sin(ang)
    x_axis_line = QgsLineString([
        QgsPointXY(ox, oy),
        QgsPointXY(x_end_x, x_end_y)
    ])
    x_axis_geom = QgsGeometry(x_axis_line)

    # Y-axis (dark blue) - pointing up from origin
    y_end_x = ox - y_axis_length * math.sin(ang)
    y_end_y = oy + y_axis_length * math.cos(ang)
    y_axis_line = QgsLineString([
        QgsPointXY(ox, oy),
        QgsPointXY(y_end_x, y_end_y)
    ])
    y_axis_geom = QgsGeometry(y_axis_line)

    return [(x_axis_geom, "x_axis"), (y_axis_geom, "y_axis")]


def style_axis_layer(layer):
    """
    Apply styling to the axis layer with different colors for x and y axes,
    plus labels identifying each axis.

    Args:
        layer: The axis layer to style
    """

    x_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    x_symbol.setColor(QColor(255, 0, 0))  # Red for x-axis
    x_symbol.setWidth(1.2)

    y_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    y_symbol.setColor(QColor(0, 0, 139))  # Dark blue for y-axis
    y_symbol.setWidth(1.2)

    categories = [
        QgsRendererCategory("x_axis", x_symbol, "Cross-shore (x)"),
        QgsRendererCategory("y_axis", y_symbol, "Longshore (y)")
    ]

    renderer = QgsCategorizedSymbolRenderer("axis_type", categories)
    layer.setRenderer(renderer)

    _enable_axis_labels(layer)
    layer.triggerRepaint()


def _enable_axis_labels(layer):
    """Label each axis with 'Cross-shore (x)' / 'Longshore (y)' in a text box."""
    from qgis.core import (
        QgsPalLayerSettings, QgsTextFormat, QgsTextBackgroundSettings,
        QgsVectorLayerSimpleLabeling,
    )

    settings = QgsPalLayerSettings()
    settings.fieldName = (
        "CASE WHEN \"axis_type\" = 'x_axis' THEN 'Cross-shore (x)' "
        "ELSE 'Longshore (y)' END"
    )
    settings.isExpression = True
    # Place the label along the axis line.
    settings.placement = QgsPalLayerSettings.Line

    text_format = QgsTextFormat()
    text_format.setSize(9)

    # White rounded text box behind the label so it reads on any basemap.
    background = QgsTextBackgroundSettings()
    background.setEnabled(True)
    background.setType(QgsTextBackgroundSettings.ShapeRectangle)
    background.setFillColor(QColor(255, 255, 255, 220))
    background.setStrokeColor(QColor(80, 80, 80))
    background.setStrokeWidth(0.2)
    text_format.setBackground(background)

    settings.setFormat(text_format)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def update_axes_visualization(origin_point, w, h, ang_deg, is_xbeach_origin=False):
    """
    Update or clear the axes visualization based on anchor mode.

    Args:
        origin_point: Origin point (QgsPointXY)
        w: Width in map units
        h: Height in map units
        ang_deg: Rotation angle in degrees
        is_xbeach_origin: Whether to show XBeach origin axes
    """
    if is_xbeach_origin and origin_point:
        axis_lyr = axis_layer()
        axis_lyr.startEditing()
        axis_lyr.dataProvider().truncate()

        axis_lines = create_axis_lines(origin_point, w, h, ang_deg)

        for i, (geom, axis_type) in enumerate(axis_lines):
            f = QgsFeature(axis_lyr.fields())
            f.setGeometry(geom)
            f["id"] = i + 1
            f["axis_type"] = axis_type
            axis_lyr.addFeature(f)

        style_axis_layer(axis_lyr)

        axis_lyr.commitChanges()
        axis_lyr.triggerRepaint()

        update_origin_point_visualization(origin_point, is_xbeach_origin)
    else:
        # Clear without creating the layers.
        clear_existing_xbeach_layers()

    set_xbeach_layers_visibility(is_xbeach_origin)


def origin_point_layer():
    """
    Get or create a temporary origin point layer for XBeach origin visualization.

    Returns:
        QgsVectorLayer: The origin point layer
    """
    prj = QgsProject.instance()
    lst = prj.mapLayersByName(ORIGIN_POINT_LAYER_NAME)
    if lst:
        return lst[0]
    vl = QgsVectorLayer(f"Point?crs={get_working_crs().authid()}", ORIGIN_POINT_LAYER_NAME, "memory")
    vl.dataProvider().addAttributes([
        QgsField("id", QVariant.Int),
        QgsField("type", QVariant.String)
    ])
    vl.updateFields()
    add_layer_to_group(vl)
    return vl


def style_origin_point_layer(layer):
    """
    Apply styling to the origin point layer with an X symbol.

    Args:
        layer: The origin point layer to style
    """

    symbol = QgsMarkerSymbol.createSimple({
        'name': 'cross2',  # X symbol
        'color': '255,0,0',  # Red color
        'size': '8',
        'outline_color': '0,0,0',  # Black outline
        'outline_width': '1'
    })

    renderer = QgsSingleSymbolRenderer(symbol)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def update_origin_point_visualization(origin_point, is_xbeach_origin=False):
    """
    Update or clear the origin point visualization.

    Args:
        origin_point: Origin point (QgsPointXY)
        is_xbeach_origin: Whether to show XBeach origin point
    """
    if is_xbeach_origin and origin_point:
        origin_lyr = origin_point_layer()
        origin_lyr.startEditing()
        origin_lyr.dataProvider().truncate()

        f = QgsFeature(origin_lyr.fields())
        f.setGeometry(QgsGeometry.fromPointXY(origin_point))
        f["id"] = 1
        f["type"] = "xbeach_origin"
        origin_lyr.addFeature(f)

        style_origin_point_layer(origin_lyr)

        origin_lyr.commitChanges()
        origin_lyr.triggerRepaint()


def clear_xbeach_layers():
    """
    Clear all XBeach-specific temporary layers (axes and origin point).
    This is called when switching away from XBeach coordinate origin mode.
    """
    clear_existing_xbeach_layers()

    set_xbeach_layers_visibility(False)


def set_xbeach_layers_visibility(visible=True):
    """
    Set the visibility of XBeach temporary layers.

    Args:
        visible: Whether to show or hide the XBeach layers
    """
    prj = QgsProject.instance()

    axis_layers = prj.mapLayersByName(AXIS_LAYER_NAME)
    if axis_layers:
        layer_tree_layer = prj.layerTreeRoot().findLayer(axis_layers[0].id())
        if layer_tree_layer:
            layer_tree_layer.setItemVisibilityChecked(visible)

    origin_layers = prj.mapLayersByName(ORIGIN_POINT_LAYER_NAME)
    if origin_layers:
        layer_tree_layer = prj.layerTreeRoot().findLayer(origin_layers[0].id())
        if layer_tree_layer:
            layer_tree_layer.setItemVisibilityChecked(visible)


def clear_existing_xbeach_layers():
    """
    Clear existing XBeach layers if they exist, but don't create new ones.
    """
    prj = QgsProject.instance()

    axis_layers = prj.mapLayersByName(AXIS_LAYER_NAME)
    if axis_layers:
        axis_layer = axis_layers[0]
        axis_layer.startEditing()
        axis_layer.dataProvider().truncate()
        axis_layer.commitChanges()
        axis_layer.triggerRepaint()

    origin_layers = prj.mapLayersByName(ORIGIN_POINT_LAYER_NAME)
    if origin_layers:
        origin_layer = origin_layers[0]
        origin_layer.startEditing()
        origin_layer.dataProvider().truncate()
        origin_layer.commitChanges()
        origin_layer.triggerRepaint()
