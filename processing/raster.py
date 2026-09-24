"""
Raster processing functions for SCOPE.
"""
import os
import tempfile
from datetime import datetime
from pathlib import Path
from osgeo import gdal, ogr, osr

from ..utils.geometry import reproject_geom
from ..utils.constants import get_working_crs, NODATA_VAL
from .grid import create_grids_gui


def clip_translate_grid_gui(raster, rect_geom, ll, centre, w, h, ang_deg, dx, dy, create_grids, log_func,
                           coord_system="local", use_adaptive_grid=False,
                           min_cell_size=None, max_cell_size=None, anchor_mode="Center",
                           custom_grid_definitions=None,
                           threshold_layers=None, threshold_default_value=complex(1.0, 0.0),
                           output_prefix=None, create_visualization=True,
                           adaptive_z_threshold=None, adaptive_transition_factor=None,
                           show_grid_spacing_preview=False, show_bed_2d_preview=False,
                           show_bed_3d_preview=False, show_custom_grid_preview=False,
                           xyz_path=None, log_path=None):
    """
    Clip a raster to the model area, export it as XYZ and build the grids from it.

    Args:
        raster: QgsRasterLayer to process
        rect_geom: Rectangle geometry
        ll: Lower-left point (QgsPointXY)
        centre: Centre point tuple (x, y)
        w: Width in map units
        h: Height in map units
        ang_deg: Rotation angle in degrees
        dx: Grid spacing in x direction
        dy: Grid spacing in y direction
        create_grids: Whether to create grid files
        log_func: Logging function
        coord_system: Coordinate system to use ("local" or "world")
        use_adaptive_grid: Whether to use adaptive grid resolution
        min_cell_size: Minimum cell size for adaptive grid
        max_cell_size: Maximum cell size for adaptive grid
        adaptive_z_threshold: Z-threshold for fine grid zone (z > threshold)
        adaptive_transition_factor: Precomputed transition factor (>1), optional
        anchor_mode: Anchor mode for rotation ("Center" or "XBeach coordinate origin")
        custom_grid_definitions: List of CustomGridDefinition objects to generate
        threshold_layers: Dictionary of threshold layers and values
        threshold_default_value: Default threshold value for complex numbers
        output_prefix: Prefix for output files (used for split areas)
        create_visualization: Add the processed area layers to the map
        show_*_preview: Open the corresponding matplotlib preview pane
        xyz_path: Where to write the clipped XYZ; grids go to the same folder
        log_path: Run log file to append to, or None for no file log
    """
    base_log_func = log_func
    runtime_log_path = Path(log_path) if log_path else None
    xyz_path = Path(xyz_path)

    def _write_log_file(message):
        if runtime_log_path is None:
            return
        runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        with runtime_log_path.open("a", encoding="utf-8") as lf:
            lf.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

    def log_func(message):
        base_log_func(message)
        try:
            _write_log_file(message)
        except Exception:
            pass

    def _write_run_header():
        """Write the run settings to the log file so a run can be reproduced from it."""
        log_func("=" * 60)
        log_func(f"SCOPE run started {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_func(f"Raster: {raster_name}")
        log_func(f"Working CRS: {get_working_crs().authid()}")
        log_func(
            f"Domain: width={w:.3f} m, height={h:.3f} m, "
            f"rotation={ang_deg:.3f} deg, anchor={anchor_mode}"
        )
        log_func(f"Coordinate output: {coord_system}")
        if use_adaptive_grid:
            log_func(
                f"Adaptive grid: min cell={min_cell_size} m, max cell={max_cell_size} m, "
                f"threshold z={adaptive_z_threshold} m, longshore spacing={dy} m"
            )
        else:
            log_func(f"Uniform grid spacing: dx={dx} m, dy={dy} m")
        if custom_grid_definitions:
            names = [d.sanitized_filename() for d in custom_grid_definitions if d.enabled]
            log_func(f"Custom grid files: {', '.join(names) if names else 'none enabled'}")
        if threshold_layers:
            layer_desc = ", ".join(f"{layer.name()}={val}" for layer, val in threshold_layers.items())
            log_func(f"Threshold mask layers: {layer_desc}, default={threshold_default_value}")
        if output_prefix:
            log_func(f"Sub area prefix: {output_prefix}")
        log_func("=" * 60)

    raster_path = raster.dataProvider().dataSourceUri()
    raster_crs = raster.crs()
    raster_name = raster.name()

    if runtime_log_path is not None:
        _write_run_header()

    # Extract data beyond the model area so interpolation near its edges has support.
    buffer_distance = 50.0
    log_func(f"Expanding data extraction area by {buffer_distance}m for better boundary interpolation...")
    expanded_rect_geom = rect_geom.buffer(buffer_distance, 5)

    if create_visualization:
        from qgis.core import QgsVectorLayer, QgsFeature, QgsSymbol, QgsSingleSymbolRenderer
        from qgis.PyQt.QtGui import QColor
        from ..utils.layer_utils import (
            add_layer_to_subgroup, clear_subgroup, PROCESSED_AREA_SUBGROUP,
        )

        crs_authid = get_working_crs().authid()

        def _make_area_layer(name, geometry, fill_rgba, stroke_rgb, stroke_width):
            layer = QgsVectorLayer(f"Polygon?crs={crs_authid}", name, "memory")
            feat = QgsFeature()
            feat.setGeometry(geometry)
            layer.dataProvider().addFeature(feat)
            symbol = QgsSymbol.defaultSymbol(layer.geometryType()).clone()
            symbol.setColor(QColor(*fill_rgba))
            symbol.symbolLayer(0).setStrokeColor(QColor(*stroke_rgb))
            symbol.symbolLayer(0).setStrokeWidth(stroke_width)
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()
            return layer

        # Replace the previous run's layers so they do not pile up.
        clear_subgroup(PROCESSED_AREA_SUBGROUP)

        # Viridis colours (#440154, #21918c) for colour-blind readability.
        buffer_layer = _make_area_layer(
            "Data extraction buffer", expanded_rect_geom,
            fill_rgba=(68, 1, 84, 35), stroke_rgb=(68, 1, 84), stroke_width=0.5,
        )
        add_layer_to_subgroup(buffer_layer, PROCESSED_AREA_SUBGROUP, at_top=True)

        model_layer = _make_area_layer(
            "Model area", rect_geom,
            fill_rgba=(33, 145, 140, 60), stroke_rgb=(33, 145, 140), stroke_width=0.8,
        )
        add_layer_to_subgroup(model_layer, PROCESSED_AREA_SUBGROUP, at_top=True)

        log_func(f"Updated '{PROCESSED_AREA_SUBGROUP}' (Model area + Data extraction buffer)")

    poly_raster = reproject_geom(expanded_rect_geom, get_working_crs(), raster_crs)

    # GDAL needs the cutline as a file.
    td = tempfile.mkdtemp()
    shp_path = os.path.join(td, "cut.shp")
    drv = ogr.GetDriverByName("ESRI Shapefile")
    ds = drv.CreateDataSource(shp_path)
    cut_srs = osr.SpatialReference()
    cut_srs.ImportFromWkt(raster_crs.toWkt())
    lyr = ds.CreateLayer("cut", srs=cut_srs, geom_type=ogr.wkbPolygon)
    lyr.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
    feat = ogr.Feature(lyr.GetLayerDefn())
    feat.SetField("id", 1)
    feat.SetGeometry(ogr.CreateGeometryFromWkb(poly_raster.asWkb()))
    lyr.CreateFeature(feat)
    ds = None

    tmp_clip = Path(tempfile.gettempdir()) / f"clip_tmp_{raster_name}.tif"
    gdal.Warp(
        tmp_clip.as_posix(),
        raster_path,
        format="GTiff",
        cutlineDSName=shp_path,
        cropToCutline=True,
        dstNodata=NODATA_VAL,
    )

    tmp_warp = Path(tempfile.gettempdir()) / f"clip_tmp_warp_{raster_name}.tif"
    gdal.Warp(
        tmp_warp.as_posix(),
        tmp_clip.as_posix(),
        dstSRS=get_working_crs().authid(),
        resampleAlg="near",
        dstNodata=NODATA_VAL,
    )

    xyz_path.parent.mkdir(parents=True, exist_ok=True)
    log_func(f"Saving {raster_name} to: {xyz_path}")
    xyz_path.unlink(missing_ok=True)

    gdal.Translate(xyz_path.as_posix(), tmp_warp.as_posix(), format="XYZ")

    if xyz_path.is_file():
        log_func(f"XYZ written: {xyz_path}")
        if create_grids:
            create_grids_gui(ll, centre, w, h, ang_deg, dx, dy, xyz_path, xyz_path.parent, log_func,
                           coord_system, use_adaptive_grid, min_cell_size, max_cell_size, anchor_mode,
                           custom_grid_definitions, threshold_layers, threshold_default_value,
                           output_prefix=output_prefix,
                           adaptive_z_threshold=adaptive_z_threshold,
                           adaptive_transition_factor=adaptive_transition_factor,
                           show_grid_spacing_preview=show_grid_spacing_preview,
                           show_bed_2d_preview=show_bed_2d_preview,
                           show_bed_3d_preview=show_bed_3d_preview,
                           show_custom_grid_preview=show_custom_grid_preview,
                           raster_name=raster_name)
    else:
        log_func(f"Translate finished but XYZ missing for {raster_name}!")

    tmp_clip.unlink(missing_ok=True)
    tmp_warp.unlink(missing_ok=True)
    for ext in (".shp", ".shx", ".dbf", ".prj"):
        Path(shp_path.replace(".shp", ext)).unlink(missing_ok=True)
    os.rmdir(td)
