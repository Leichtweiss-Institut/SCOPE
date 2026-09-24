"""
Constants and configuration for SCOPE.
"""
from qgis.core import QgsCoordinateReferenceSystem, QgsProject

# Coordinate Reference System
# EPSG:3034 is kept only as a last-resort fallback; the active working CRS is
# normally the QGIS project CRS (or a CRS the user picks in the GUI).
CRS_3034 = QgsCoordinateReferenceSystem("EPSG:3034")

# Session-wide working CRS. ``None`` means "use the current project CRS".
_WORKING_CRS = None


def set_working_crs(crs):
    """Set the working CRS for the current session.

    Args:
        crs: A QgsCoordinateReferenceSystem or an authid string (e.g. "EPSG:25832").
            Pass ``None`` to fall back to the project CRS.
    """
    global _WORKING_CRS
    if crs is None:
        _WORKING_CRS = None
    elif isinstance(crs, str):
        _WORKING_CRS = QgsCoordinateReferenceSystem(crs)
    else:
        _WORKING_CRS = crs


def get_working_crs():
    """Return the active working CRS.

    Resolution order: an explicitly set working CRS, otherwise the current
    QGIS project CRS, otherwise EPSG:3034 as a final fallback.
    """
    if _WORKING_CRS is not None and _WORKING_CRS.isValid():
        return _WORKING_CRS
    project_crs = QgsProject.instance().crs()
    if project_crs.isValid():
        return project_crs
    return CRS_3034

# Temporary layer names
AXIS_LAYER_NAME = "XBeach axes"
ORIGIN_POINT_LAYER_NAME = "XBeach origin"

# No data value for raster operations
NODATA_VAL = 0.0  # Value used during warp/translate and filtered in XYZ
