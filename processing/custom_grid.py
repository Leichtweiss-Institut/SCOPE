"""
Custom grid files: one value per polygon layer, assigned to every grid node
inside that layer's polygons, over a default background value. Used for
vegetation maps, XBeach hard layers (ne_layer.grd), bed friction and similar.

Values are evaluated at the nodes, so each grid has the shape of x.grd, y.grd
and z.grd, as XBeach (nx+1, ny+1) and AeoLiS both require.

Containment is tested with a QGIS R-tree index, a bounding-box pre-filter and
an exact point-in-polygon test, so run time scales roughly with node count.
"""
import os
import time
import traceback
import numpy as np
from qgis.core import (
    QgsProject,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsFeature,
    QgsApplication,
    QgsRectangle,
)

from ..utils.constants import get_working_crs

try:
    from qgis.PyQt import sip
except ImportError:  # pragma: no cover - very old QGIS builds
    sip = None


class CustomGridDefinition:
    """One user-defined custom grid file built from polygon layers.

    Attributes:
        filename: Output file name, e.g. "veg.grd".
        layer_values: {QgsVectorLayer: float} value assigned per layer.
        default_value: Background value for nodes covered by no layer.
        decimals: Output decimal places; 0 writes integers.
        enabled: Whether this grid is generated during processing.
        show_preview: Whether a preview pane is opened for this grid.
    """

    def __init__(self, filename="", layer_values=None, default_value=0.0,
                 decimals=3, enabled=True, show_preview=True):
        self.filename = filename
        self.layer_values = layer_values or {}
        self.default_value = default_value
        self.decimals = decimals
        self.enabled = enabled
        self.show_preview = show_preview

    def sanitized_filename(self):
        """Return the trimmed filename, appending '.grd' when no extension is given."""
        name = self.filename.strip()
        if name and "." not in name:
            name += ".grd"
        return name

    def valid_layer_values(self):
        """Return layer_values restricted to layers still alive in the project."""
        live_ids = set(QgsProject.instance().mapLayers().keys())
        valid = {}
        for layer, value in self.layer_values.items():
            if sip is not None and sip.isdeleted(layer):
                continue
            if layer.id() in live_ids:
                valid[layer] = value
        return valid

    def copy(self):
        """Return an independent copy (shares layer references, not the dict)."""
        return CustomGridDefinition(
            filename=self.filename,
            layer_values=dict(self.layer_values),
            default_value=self.default_value,
            decimals=self.decimals,
            enabled=self.enabled,
            show_preview=self.show_preview,
        )


def create_custom_grids(XA, YA, origin_x, origin_y, out_dir, log_func, definitions,
                        coord_system="local", output_prefix=None):
    """
    Create all enabled custom grid files using QGIS spatial indexing.

    Node values are evaluated at the grid nodes using point-in-polygon
    containment against each definition's polygon layers. Layers are processed
    in order; later layers override earlier ones where they overlap.

    Args:
        XA, YA: Grid coordinate arrays (node coordinates, shape (ny, nx)).
        origin_x, origin_y: Grid origin coordinates.
        out_dir: Output directory path.
        log_func: Function to log progress messages.
        definitions: List of CustomGridDefinition objects.
        coord_system: "local" or "world" coordinate system.
        output_prefix: Optional prefix for output file names (split areas).

    Returns:
        bool: True if every enabled grid was written successfully.
    """
    definitions = [d for d in definitions if d.enabled]
    if not definitions:
        return True

    ny, nx = XA.shape
    total_nodes = ny * nx

    log_func("CUSTOM GRID CREATION STARTED")
    log_func(f"Grid size: {total_nodes:,} nodes ({nx}×{ny})")
    log_func(f"Custom grid files to create: {len(definitions)}")
    log_func("-" * 60)

    # Grid bounds are used to discard polygons that cannot contain any grid node.
    x_min, x_max = float(XA.min()), float(XA.max())
    y_min, y_max = float(YA.min()), float(YA.max())
    grid_bounds = QgsRectangle(x_min, y_min, x_max, y_max)
    log_func(f"Grid bounds: X({x_min:.2f}, {x_max:.2f}), Y({y_min:.2f}, {y_max:.2f})")

    all_ok = True
    for defn in definitions:
        out_name = defn.sanitized_filename()
        if output_prefix:
            out_name = f"{output_prefix}_{out_name}"
        try:
            ok = _create_one_grid(
                XA, YA, grid_bounds, origin_x, origin_y,
                out_dir, out_name, log_func, defn, coord_system
            )
        except Exception as e:
            log_func(f"Error creating custom grid '{out_name}': {str(e)}")
            log_func(f"Stack trace: {traceback.format_exc()}")
            ok = False
        all_ok = all_ok and ok

    return all_ok


def _create_one_grid(XA, YA, grid_bounds, origin_x, origin_y,
                     out_dir, out_name, log_func, defn, coord_system):
    """Compute and write a single custom grid file from its definition."""
    start_time = time.time()

    ny, nx = XA.shape

    log_func(f"\nCUSTOM GRID FILE: {out_name}")
    log_func(f"   Default value (uncovered nodes): {defn.default_value}")
    log_func("-" * 60)

    # Node-shaped (ny, nx), like x.grd, y.grd and z.grd. Complex values
    # (threshold masks for AeoLiS) use a complex array.
    values = [defn.default_value, *defn.layer_values.values()]
    dtype = np.complex128 if any(isinstance(v, complex) for v in values) else np.float64
    grid = np.full((ny, nx), defn.default_value, dtype=dtype)

    # Prepare layers (transform, localize, validate, bounds pre-filter).
    log_func("PROCESSING POLYGON LAYERS:")
    target_crs = get_working_crs()
    layer_values = defn.valid_layer_values()
    if len(layer_values) < len(defn.layer_values):
        log_func("   Warning: some selected layers no longer exist in the project and were skipped.")

    processed_layers = _process_layers(
        layer_values, target_crs, origin_x, origin_y, coord_system, grid_bounds, log_func
    )

    total_layers = len([l for l in processed_layers.values() if l[0]])
    if total_layers == 0:
        log_func(f"WARNING: No valid geometries found in any layer for {out_name}.")
        return False

    log_func(f"\nPROCESSING {total_layers} LAYER(S):")

    layer_count = 0
    total_nodes_updated = 0

    for layer_name, (geometries, value) in processed_layers.items():
        if not geometries:
            continue

        layer_count += 1
        layer_start_time = time.time()

        log_func(f"   [{layer_count:2d}/{total_layers}] Processing '{layer_name}' "
                 f"(value={value})...")

        # Keep the UI responsive.
        QgsApplication.processEvents()

        nodes_updated = _process_layer(
            geometries, value, XA, YA, grid, nx, ny,
            layer_start_time, log_func
        )

        layer_time = time.time() - layer_start_time
        total_nodes_updated += nodes_updated
        coverage_percent = (nodes_updated / (ny * nx)) * 100

        log_func(f"            Updated {nodes_updated:,} nodes ({coverage_percent:.2f}% coverage)")
        log_func(f"            Layer completed in {layer_time:.2f}s")

    total_time = time.time() - start_time

    log_func("\nPROCESSING COMPLETE:")
    log_func(f"   Total nodes updated: {total_nodes_updated:,}/{ny*nx:,} "
             f"({(total_nodes_updated/(ny*nx))*100:.2f}%)")
    log_func(f"   Processing time: {total_time:.2f}s")
    log_func(f"   Average speed: {(ny*nx)/total_time:,.0f} nodes/second")

    log_func("\nSAVING RESULTS:")
    return _write_grid(grid, out_dir, out_name, defn.decimals, log_func)


def _process_layers(layer_values, target_crs, origin_x, origin_y,
                    coord_system, grid_bounds, log_func):
    """
    Transform, localize, validate and bounds-filter the polygon layers.

    Returns ``{layer_name: (geometries, value)}`` where geometries are already
    in the working CRS / local coordinates and only those whose bounding box
    intersects the grid are retained.
    """
    processed_layers = {}

    for i, (layer, value) in enumerate(layer_values.items(), 1):
        log_func(f"   [{i}/{len(layer_values)}] Processing '{layer.name()}' "
                 f"(value={value})...")

        layer_crs = layer.crs()
        total_features = layer.featureCount()
        log_func(f"       Layer CRS: {layer_crs.authid()} → Target: {target_crs.authid()}")
        log_func(f"       Features to process: {total_features:,}")

        if total_features == 0:
            log_func("       Layer is empty, skipping")
            processed_layers[layer.name()] = ([], value)
            continue

        # Reuse a single coordinate transform per layer.
        transform = None
        if layer_crs != target_crs:
            transform = QgsCoordinateTransform(layer_crs, target_crs, QgsProject.instance())

        geometries = []
        valid_geometries = 0
        invalid_geometries = 0
        filtered_out = 0

        for feat in layer.getFeatures():
            geom = QgsGeometry(feat.geometry())

            if transform is not None:
                try:
                    geom.transform(transform)
                except Exception:
                    invalid_geometries += 1
                    continue

            # Translate to local coordinates when requested.
            if coord_system == "local":
                geom.translate(-origin_x, -origin_y)

            if not geom.isGeosValid() or geom.isEmpty():
                invalid_geometries += 1
                continue

            # Drop polygons that cannot contain any grid node.
            if not grid_bounds.intersects(geom.boundingBox()):
                filtered_out += 1
                continue

            geometries.append(geom)
            valid_geometries += 1

        log_func(f"       Valid geometries: {valid_geometries:,}/{total_features:,}")
        if invalid_geometries > 0:
            log_func(f"       Invalid geometries: {invalid_geometries:,}")
        if filtered_out > 0:
            log_func(f"       Filtered out (outside grid): {filtered_out:,}")
        log_func(f"       Processing completed ({valid_geometries:,} geometries retained)")

        processed_layers[layer.name()] = (geometries, value)

    return processed_layers


def _process_layer(geometries, value, XA, YA, grid, nx, ny,
                   layer_start_time, log_func):
    """
    Assign ``value`` to every grid node that lies inside one of
    ``geometries``, using a spatial index with cached bounding boxes.
    """
    if not geometries:
        return 0

    log_func(f"            Building spatial index for {len(geometries):,} features...")

    spatial_index = QgsSpatialIndex()
    geom_dict = {}
    geom_bounds = {}

    for i, geom in enumerate(geometries):
        feat = QgsFeature()
        feat.setGeometry(geom)
        feat.setId(i)
        spatial_index.addFeature(feat)
        geom_dict[i] = geom
        geom_bounds[i] = geom.boundingBox()  # Cache bounding boxes once.

    log_func("            Spatial index created with cached bounds")
    log_func("            Checking node containment...")

    nodes_updated = 0
    total_nodes = ny * nx

    # Batch only to keep the UI responsive; batching does not affect the result.
    batch_size = 50000

    for batch_start in range(0, total_nodes, batch_size):
        batch_end = min(batch_start + batch_size, total_nodes)

        for node_idx in range(batch_start, batch_end):
            i = node_idx // nx
            j = node_idx % nx

            x_node = float(XA[i, j])
            y_node = float(YA[i, j])
            node_point = QgsPointXY(x_node, y_node)

            # Bounding-box pre-filter on the nearest candidate features.
            candidate_ids = []
            for geom_id in spatial_index.nearestNeighbor(node_point, 10):
                bounds = geom_bounds[geom_id]
                if (bounds.xMinimum() <= x_node <= bounds.xMaximum() and
                        bounds.yMinimum() <= y_node <= bounds.yMaximum()):
                    candidate_ids.append(geom_id)

            # Exact point-in-polygon only for candidates that pass the bbox test.
            for geom_id in candidate_ids:
                if geom_dict[geom_id].contains(node_point):
                    grid[i, j] = value
                    nodes_updated += 1
                    break  # Found a containing polygon; move on.

        # Update the UI and report progress once per batch.
        QgsApplication.processEvents()
        progress = (batch_end / total_nodes) * 100
        log_func(f"            Progress: {progress:.1f}% ({batch_end:,}/{total_nodes:,} nodes)")
        elapsed = time.time() - layer_start_time
        if elapsed > 0 and batch_end > 0:
            estimated_remaining = (total_nodes - batch_end) / (batch_end / elapsed)
            log_func(f"            ETA: {estimated_remaining:.1f} seconds remaining")

    return nodes_updated


def _write_grid(grid, out_dir, out_name, decimals, log_func):
    """Write one grid to disk as space-separated text rows.

    Complex grids are written at full precision in the (real+imagj) form that
    AeoLiS reads; real grids use ``decimals`` places, and 0 writes integers.
    """
    try:
        out_file = os.path.join(out_dir, out_name)
        is_complex = np.iscomplexobj(grid)

        precision = "full precision, complex" if is_complex else f"{decimals} decimal places"
        log_func(f"   Writing: {os.path.basename(out_file)} ({grid.size:,} values, {precision})")

        estimated_size_mb = (grid.size * 8) / (1024 * 1024)
        log_func(f"   Estimated file size: {estimated_size_mb:.1f} MB")

        with open(out_file, 'w') as f:
            ny, nx = grid.shape
            for i in range(ny):
                if is_complex:
                    row_values = [f"({v.real:.18e}{v.imag:+.18e}j)" for v in grid[i]]
                elif decimals == 0:
                    row_values = [str(int(round(grid[i, j]))) for j in range(nx)]
                else:
                    row_values = [f"{grid[i, j]:.{decimals}f}" for j in range(nx)]
                f.write(" ".join(row_values) + "\n")

        actual_size_mb = os.path.getsize(out_file) / (1024 * 1024)
        log_func(f"   File written: {actual_size_mb:.1f} MB")
        return True

    except Exception as e:
        log_func(f"   Error writing custom grid '{out_name}': {str(e)}")
        return False
