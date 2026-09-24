"""
Adaptive cross-shore node layouts and the AeoLiS threshold mask.
"""
import math
import numpy as np
from qgis.core import QgsProject, QgsCoordinateTransform, QgsGeometry, QgsPointXY, QgsFeature

from SCOPE.utils.constants import get_working_crs


def create_threshold_mask_grid(XA, YA, origin_x, origin_y, out_dir, log_func, threshold_layers,
                               coord_system="local", threshold_default_value=complex(1.0, 0.0),
                               out_name="threshold_mask.grd"):
    """
    Create threshold_mask.grd for AeoLiS from polygon layers with complex values.

    Each cell takes the value of the layer covering the largest share of its
    area, and that value is written to the cell's four corner nodes so the
    mask has the same shape as x.grd, y.grd and z.grd.

    Args:
        XA, YA: Node coordinate arrays of shape (ny, nx)
        origin_x, origin_y: Origin subtracted from geometries in local mode
        out_dir: Output directory
        log_func: Logging function
        threshold_layers: Dictionary of {layer: complex_value}
        coord_system: "local" or "world"
        threshold_default_value: Value for nodes not covered by any layer
        out_name: Output filename
    """
    if not threshold_layers:
        log_func("No threshold layers provided. Skipping threshold_mask.grd creation.")
        return

    log_func(f"Creating threshold mask grid with {len(threshold_layers)} layer(s) using {coord_system} coordinates...")
    log_func(f"Default threshold value: {threshold_default_value}")

    ny, nx = XA.shape

    target_crs = get_working_crs()
    processed_threshold_layers = {}

    for layer, val in threshold_layers.items():
        layer_crs = layer.crs()
        transform = None
        if layer_crs != target_crs:
            transform = QgsCoordinateTransform(layer_crs, target_crs, QgsProject.instance())

        processed_features = []
        for feat in layer.getFeatures():
            geom = QgsGeometry(feat.geometry())
            if transform is not None:
                geom.transform(transform)
            if coord_system == "local":
                geom.translate(-origin_x, -origin_y)

            feat_new = QgsFeature(feat)
            feat_new.setGeometry(geom)
            processed_features.append(feat_new)

        processed_threshold_layers[layer.name()] = (processed_features, val)

    threshold_mask = np.full_like(XA, threshold_default_value, dtype=complex)

    log_func(f"Processing grid cells: {ny - 1} x {nx - 1}")

    total_cells = (ny - 1) * (nx - 1)
    cells_with_threshold = 0

    for ri in range(ny - 1):
        for cj in range(nx - 1):
            p1 = QgsPointXY(XA[ri, cj], YA[ri, cj])
            p2 = QgsPointXY(XA[ri, cj+1], YA[ri, cj+1])
            p3 = QgsPointXY(XA[ri+1, cj+1], YA[ri+1, cj+1])
            p4 = QgsPointXY(XA[ri+1, cj], YA[ri+1, cj])
            cell_poly = QgsGeometry.fromPolygonXY([[p1, p2, p3, p4, p1]])

            # The layer with the largest intersection area wins the cell.
            max_cov = 0
            assigned_val = threshold_default_value
            for feats, val in processed_threshold_layers.values():
                cov = 0
                for feat in feats:
                    if feat.geometry().intersects(cell_poly):
                        inter = feat.geometry().intersection(cell_poly)
                        if not inter.isEmpty():
                            cov += inter.area()

                if cov > max_cov:
                    max_cov = cov
                    assigned_val = val

            if assigned_val != threshold_default_value:
                cells_with_threshold += 1
                threshold_mask[ri, cj] = assigned_val
                threshold_mask[ri, cj+1] = assigned_val
                threshold_mask[ri+1, cj] = assigned_val
                threshold_mask[ri+1, cj+1] = assigned_val

    threshold_mask_path = out_dir / out_name

    if not np.any(threshold_mask != threshold_default_value):
        log_func("WARNING: No threshold values found in grid! Check if threshold layers intersect with the grid area.")

    log_func(f"Writing threshold mask to: {threshold_mask_path}")
    log_func(f"Total cells processed: {total_cells}, cells with custom values: {cells_with_threshold}")

    try:
        # AeoLiS reads complex values in the form (real+imagj).
        with threshold_mask_path.open("w", encoding="utf-8") as f:
            for ri in range(ny):
                row_values = []
                for cj in range(nx):
                    val = threshold_mask[ri, cj]
                    row_values.append(f"({val.real:.18e}{val.imag:+.18e}j)")
                f.write(" ".join(row_values) + "\n")

        log_func(f"Threshold mask grid written successfully: {threshold_mask_path}")

        unique_values = np.unique(threshold_mask)
        log_func("Threshold mask statistics:")
        log_func(f"  Unique values: {len(unique_values)}")
        for val in unique_values:
            count = np.sum(threshold_mask == val)
            percentage = (count / threshold_mask.size) * 100
            log_func(f"  Value {val}: {count} nodes ({percentage:.1f}%)")

    except Exception as e:
        log_func(f"Error writing threshold mask grid: {e}")
        return False

    return True


def create_left_to_right_adaptive_grid(width, height, dy, min_cell_size, max_cell_size, log_func=None):
    """
    Fallback layout: cell size decreases linearly from left to right.

    Used when no threshold crossing can be found. The last cell is kept at full
    size, so the grid may extend slightly beyond ``width``.

    Args:
        width, height: Domain size
        dy: Longshore spacing
        min_cell_size: Cell size at the right (landward) edge
        max_cell_size: Cell size at the left (offshore) edge
        log_func: Optional logging function

    Returns:
        tuple: (x_coords, y_coords) node positions in local coordinates
    """
    if log_func:
        log_func(f"Creating left-to-right adaptive grid: {max_cell_size}m (left) to {min_cell_size}m (right)")

    ny = int(np.ceil(height / dy)) + 1
    y_coords = np.linspace(0, height, ny)

    x_coords = [0.0]
    x = 0.0

    while x < width:
        progress = x / width
        current_cell_size = max_cell_size * (1 - progress) + min_cell_size * progress

        # Close with a full cell rather than a small remainder.
        if width - x <= current_cell_size:
            x += current_cell_size
            x_coords.append(x)
            break

        x += current_cell_size
        x_coords.append(x)

        if len(x_coords) > 10000:
            if log_func:
                log_func("Warning: Too many grid points generated, stopping refinement")
            break

    x_coords = np.array(x_coords)

    # Boundary cells take the size of their neighbours.
    if x_coords.size >= 3:
        dx_vals = np.diff(x_coords)
        dx_vals[0] = dx_vals[1]
        dx_vals[-1] = dx_vals[-2]
        x_coords = np.concatenate(([0.0], np.cumsum(dx_vals)))

    nx = len(x_coords)

    if log_func:
        actual_width = x_coords[-1] - x_coords[0]
        coverage_percent = (actual_width / width) * 100
        log_func(f"Generated adaptive grid: {nx} x {ny} points")
        log_func(f"Domain coverage: {actual_width:.3f}m of {width:.3f}m ({coverage_percent:.1f}%)")
        if actual_width > width + 1e-9:
            log_func(f"Extended domain by {actual_width - width:.3f}m to avoid a small boundary cell.")
        if nx > 1:
            log_func(f"X-spacing ranges from {x_coords[1] - x_coords[0]:.3f}m to {x_coords[-1] - x_coords[-2]:.3f}m")

    return x_coords, y_coords


def estimate_transition_factor(min_cell_size, max_cell_size, transition_width):
    """Estimate the geometric growth factor that spans min to max cell size over a width."""
    if min_cell_size <= 0 or max_cell_size <= min_cell_size:
        return 1.0

    usable_width = max(float(transition_width), 0.0)
    if usable_width <= 0:
        return 1.0

    # Estimate number of transition cells from average spacing.
    avg_spacing = 0.5 * (min_cell_size + max_cell_size)
    n_cells = max(2, int(round(usable_width / max(avg_spacing, 1e-9))))
    ratio = max_cell_size / min_cell_size

    # n_cells cells imply n_cells-1 geometric steps.
    return float(ratio ** (1.0 / max(n_cells - 1, 1)))


def find_median_threshold_crossing(local_x, local_y, z_values, width, height, z_threshold, dy, log_func=None):
    """
    Return the median cross-shore position where elevation first exceeds z_threshold.

    Samples are binned into rows of height dy; each row contributes the smallest
    x with z > z_threshold. Returns None if no row has such a sample.
    """
    if local_x.size == 0 or local_y.size == 0 or z_values.size == 0:
        return None

    valid = (
        np.isfinite(local_x)
        & np.isfinite(local_y)
        & np.isfinite(z_values)
        & (local_x >= 0.0)
        & (local_x <= width)
        & (local_y >= 0.0)
        & (local_y <= height)
    )
    if not np.any(valid):
        return None

    x = local_x[valid]
    y = local_y[valid]
    z = z_values[valid]

    row_height = max(float(dy), 0.1)
    n_rows = max(1, int(math.ceil(height / row_height)))

    crossings = []
    for row_idx in range(n_rows):
        y0 = row_idx * row_height
        y1 = min(height, y0 + row_height)
        in_row = (y >= y0) & (y < y1 if row_idx < n_rows - 1 else y <= y1)
        if not np.any(in_row):
            continue

        row_x = x[in_row]
        row_z = z[in_row]
        above = row_z > z_threshold
        if not np.any(above):
            continue

        crossings.append(float(np.min(row_x[above])))

    if not crossings:
        if log_func:
            log_func(f"No row crossings found for z > {z_threshold:.3f}.")
        return None

    median_crossing = float(np.median(np.array(crossings, dtype=float)))
    if log_func:
        log_func(
            f"Median threshold crossing from {len(crossings)} row(s): x={median_crossing:.3f} m for z>{z_threshold:.3f}"
        )
    return median_crossing


def create_threshold_based_adaptive_grid(
    width,
    height,
    dy,
    min_cell_size,
    max_cell_size,
    crossing_x,
    transition_factor,
    log_func=None,
):
    """
    Threshold-driven layout: fine cells landward of crossing_x, coarsening offshore.

    - x >= crossing_x: uniform min_cell_size.
    - x < crossing_x: cells grow by transition_factor per step, capped at max_cell_size.
    - The grid is extended by less than one cell rather than closing with a small cell,
      and both boundary cells take the size of their neighbours.
    """
    ny = int(np.ceil(height / dy)) + 1
    y_coords = np.linspace(0, height, ny)

    crossing_x = float(np.clip(crossing_x, 0.0, width))
    factor = max(float(transition_factor), 1.0)

    # Build offshore cells outward from the crossing.
    left_cells = []
    remaining_left = crossing_x
    cur = min_cell_size
    guard = 0

    while remaining_left > 1e-9 and guard < 200000:
        guard += 1
        cell = min(cur, max_cell_size, remaining_left)
        left_cells.append(cell)
        remaining_left -= cell

        if cur < max_cell_size:
            cur = min(cur * factor, max_cell_size)

    if left_cells and left_cells[-1] < min_cell_size * 0.5 and len(left_cells) > 1:
        # Merge a sliver at the offshore edge into its neighbour.
        left_cells[-2] += left_cells[-1]
        left_cells.pop()

    right_cells = []
    right_span = max(width - crossing_x, 0.0)
    n_right = int(np.ceil(right_span / max(min_cell_size, 1e-9)))
    if n_right > 0:
        right_cells = [min_cell_size] * n_right

    x_coords = [0.0]
    for cell in reversed(left_cells):
        x_coords.append(x_coords[-1] + cell)
    for cell in right_cells:
        x_coords.append(x_coords[-1] + cell)

    x_coords = np.array(x_coords, dtype=float)

    if x_coords.size >= 3:
        dx_vals = np.diff(x_coords)
        dx_vals[0] = dx_vals[1]
        dx_vals[-1] = dx_vals[-2]
        x_coords = np.concatenate(([0.0], np.cumsum(dx_vals)))

    if log_func and x_coords.size > 1:
        dx_vals = np.diff(x_coords)
        actual_width = float(x_coords[-1])
        extension = max(0.0, actual_width - width)
        log_func(
            f"Threshold-adaptive grid generated: {x_coords.size}x{ny} points, dx range {dx_vals.min():.3f}-{dx_vals.max():.3f} m"
        )
        if extension > 1e-9:
            log_func(f"Extended domain by {extension:.3f}m to avoid a small boundary cell.")

    return x_coords, y_coords
