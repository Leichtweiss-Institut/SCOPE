"""
Grid generation pipeline: interpolation, adaptive spacing and output files.
"""
from pathlib import Path

import numpy as np

from SCOPE.utils.geometry import rot_point
from SCOPE.utils.constants import get_working_crs, NODATA_VAL
from .preview import plot_custom_grid_preview, plot_grid_preview
from .threshold import (
    create_left_to_right_adaptive_grid,
    create_threshold_based_adaptive_grid,
    create_threshold_mask_grid,
    estimate_transition_factor,
    find_median_threshold_crossing,
)


def create_grids_gui(ll, centre, w, h, ang_deg, dx, dy, xyz_file: Path, out_dir: Path,
                     log_func, coord_system="local",
                     use_adaptive_grid=False, min_cell_size=None, max_cell_size=None, anchor_mode="Center",
                     custom_grid_definitions=None,
                     threshold_layers=None, threshold_default_value=complex(1.0, 0.0),
                     output_prefix=None,
                     adaptive_z_threshold=None, adaptive_transition_factor=None,
                     show_grid_spacing_preview=False, show_bed_2d_preview=False,
                     show_bed_3d_preview=False, show_custom_grid_preview=False,
                     raster_name=None):
    """
    Build a grid over the model area and write all enabled output files.

    Interpolates the XYZ samples onto a uniform or adaptive node layout, writes
    x.grd, y.grd and z.grd, then any custom grids and the threshold mask.

    Args:
        ll: Lower-left point (QgsPointXY)
        centre: Centre point tuple (x, y)
        w: Width in map units
        h: Height in map units
        ang_deg: Rotation angle in degrees
        dx: Grid spacing in x direction
        dy: Grid spacing in y direction
        xyz_file: Path to XYZ file
        out_dir: Output directory
        log_func: Logging function
        coord_system: Coordinate system to use ("local" or "world")
        use_adaptive_grid: Whether to use adaptive grid resolution
        min_cell_size: Minimum cell size for adaptive grid
        max_cell_size: Maximum cell size for adaptive grid
        anchor_mode: Anchor mode ("Center" or "XBeach coordinate origin")
        custom_grid_definitions: List of CustomGridDefinition objects to generate
        threshold_layers: Dictionary of {layer: complex_value} for the threshold mask
        threshold_default_value: Mask value for nodes outside all threshold layers
        output_prefix: Filename prefix used for split areas
        adaptive_z_threshold: Elevation that marks the start of the fine zone
        adaptive_transition_factor: Growth factor; estimated when None
        show_*_preview: Open the corresponding matplotlib preview pane
        raster_name: Raster name shown in preview titles
    """
    log_func("Creating SCOPE grids...")
    try:
        from scipy.interpolate import griddata
        SCIPY_OK = True
    except ImportError:
        SCIPY_OK = False

    def get_output_filename(base_name):
        if output_prefix:
            return f"{output_prefix}_{base_name}"
        return base_name

    try:
        xyz = np.loadtxt(xyz_file, dtype=float)
    except Exception as e:
        log_func(f"Cannot read XYZ ({e})")
        return
    if xyz.ndim == 1:
        xyz = xyz.reshape(1, 3)
    xyz = xyz[xyz[:, 2] != NODATA_VAL]  # drop NoData rows
    if xyz.size == 0:
        log_func("All XYZ rows are NoData – grid skipped!")
        return
    pts_xy = xyz[:, :2]
    pts_z = xyz[:, 2]
    grid_x = None
    grid_y = None

    cx, cy = centre

    # The rotation centre must match the one used to draw the model area.
    if anchor_mode == "XBeach coordinate origin":
        # The clicked point is both the lower-left corner and the rotation centre.
        click_point_x, click_point_y = ll.x(), ll.y()
        actual_ll_x = click_point_x
        actual_ll_y = click_point_y
        rot_center_x, rot_center_y = click_point_x, click_point_y
        log_func(f"XBeach coordinate origin mode: Using click point ({click_point_x:.2f}, {click_point_y:.2f}) as origin and rotation center")
    else:
        actual_ll_x, actual_ll_y = ll.x(), ll.y()
        rot_center_x, rot_center_y = cx, cy
        log_func(f"Center Point mode: Using center ({cx:.2f}, {cy:.2f}) as rotation center")

    # World position of the rotated lower-left corner, used as the local origin.
    origin_x, origin_y = rot_point(actual_ll_x, actual_ll_y, ang_deg, rot_center_x, rot_center_y)

    if use_adaptive_grid:
        valid_sizes = (
            min_cell_size is not None
            and max_cell_size is not None
            and min_cell_size > 0
            and max_cell_size > min_cell_size
        )

        if valid_sizes and adaptive_z_threshold is not None:
            # Rotate samples into the unrotated local frame to find row-wise crossings.
            theta = np.radians(-ang_deg)
            c, s = np.cos(theta), np.sin(theta)
            dxg = pts_xy[:, 0] - rot_center_x
            dyg = pts_xy[:, 1] - rot_center_y
            unrot_x = rot_center_x + c * dxg - s * dyg
            unrot_y = rot_center_y + s * dxg + c * dyg

            local_x = unrot_x - actual_ll_x
            local_y = unrot_y - actual_ll_y

            crossing_x = find_median_threshold_crossing(
                local_x,
                local_y,
                pts_z,
                w,
                h,
                adaptive_z_threshold,
                dy,
                log_func,
            )

            if crossing_x is None:
                log_func("No valid threshold crossing found. Falling back to left-to-right adaptive grid.")
                grid_x, grid_y = create_left_to_right_adaptive_grid(
                    w, h, dy, min_cell_size, max_cell_size, log_func
                )
            else:
                transition_factor = adaptive_transition_factor
                if transition_factor is None or transition_factor <= 1.0:
                    transition_factor = estimate_transition_factor(min_cell_size, max_cell_size, crossing_x)

                if transition_factor <= 1.0:
                    transition_factor = 1.01

                log_func(
                    f"Using threshold-driven adaptive spacing: threshold={adaptive_z_threshold:.3f} m, crossing x={crossing_x:.3f} m, factor={transition_factor:.4f}"
                )

                if transition_factor > 1.5:
                    log_func(f"WARNING: Adaptive transition factor is high ({transition_factor:.4f} > 1.5).")

                grid_x, grid_y = create_threshold_based_adaptive_grid(
                    w,
                    h,
                    dy,
                    min_cell_size,
                    max_cell_size,
                    crossing_x,
                    transition_factor,
                    log_func,
                )
        else:
            log_func("Adaptive settings incomplete. Falling back to left-to-right adaptive grid.")
            grid_x, grid_y = create_left_to_right_adaptive_grid(
                w, h, dy, min_cell_size, max_cell_size, log_func
            )

        nx = len(grid_x)
        ny = len(grid_y)
        log_func(f"Created adaptive grid with {nx}x{ny} points.")
    else:
        nx = int(np.ceil(w / dx)) + 1
        ny = int(np.ceil(h / dy)) + 1
        log_func(f"Creating uniform grid with {nx}x{ny} cells.")

    # Node coordinates in the working CRS.
    XG = np.zeros((ny, nx))
    YG = np.zeros((ny, nx))
    ZA = np.full((ny, nx), np.nan)

    if use_adaptive_grid:
        for ri in range(ny):
            for cj in range(nx):
                x_loc = actual_ll_x + grid_x[cj]
                y_loc = actual_ll_y + grid_y[ri]
                gx, gy = rot_point(x_loc, y_loc, ang_deg, rot_center_x, rot_center_y)
                XG[ri, cj], YG[ri, cj] = gx, gy
    else:
        for ri in range(ny):
            y_loc = actual_ll_y + ri * dy
            for cj in range(nx):
                x_loc = actual_ll_x + cj * dx
                gx, gy = rot_point(x_loc, y_loc, ang_deg, rot_center_x, rot_center_y)
                XG[ri, cj], YG[ri, cj] = gx, gy

    if SCIPY_OK:
        log_func("Using scipy linear interpolation (triangulation-based)...")
        grid_coords = np.column_stack([XG.ravel(), YG.ravel()])
        interpolated_values = griddata(
            points=pts_xy,
            values=pts_z,
            xi=grid_coords,
            method='linear',
            fill_value=np.nan
        )
        ZA = interpolated_values.reshape(ny, nx)

        # Nodes outside the convex hull of the samples take the nearest value.
        nan_mask = np.isnan(ZA)
        if nan_mask.any():
            log_func(f"Filling {np.sum(nan_mask)} NaN values with nearest neighbor...")
            nearest_values = griddata(
                points=pts_xy,
                values=pts_z,
                xi=grid_coords,
                method='nearest'
            )
            ZA[nan_mask] = nearest_values.reshape(ny, nx)[nan_mask]
    else:
        log_func("Scipy not available, using nearest neighbor fallback...")
        for ri in range(ny):
            for cj in range(nx):
                gx, gy = XG[ri, cj], YG[ri, cj]
                dists = np.hypot(pts_xy[:, 0] - gx, pts_xy[:, 1] - gy)
                imin = np.argmin(dists)
                ZA[ri, cj] = pts_z[imin]

    if coord_system == "local":
        XA = XG - origin_x
        YA = YG - origin_y
        log_func("Converted coordinates to local system using lower-left as origin.")
    else:
        XA = XG
        YA = YG
        log_func(f"Using world coordinates ({get_working_crs().authid()}).")

    try:
        dx_vals = np.hypot(np.diff(XA, axis=1), np.diff(YA, axis=1))
        dy_vals = np.hypot(np.diff(XA, axis=0), np.diff(YA, axis=0))
        log_func(
            f"Grid spacing summary: Δx min/max = {np.nanmin(dx_vals):.3f}/{np.nanmax(dx_vals):.3f} m, Δy min/max = {np.nanmin(dy_vals):.3f}/{np.nanmax(dy_vals):.3f} m"
        )
    except Exception as e:
        log_func(f"Could not compute spacing summary: {e}")

    if show_grid_spacing_preview or show_bed_2d_preview or show_bed_3d_preview:
        plot_grid_preview(
            XA,
            YA,
            ZA,
            log_func,
            title="Generated Grid Preview",
            show_spacing=show_grid_spacing_preview,
            show_bed_2d=show_bed_2d_preview,
            show_3d_preview=show_bed_3d_preview,
            ang_deg=ang_deg,
            raster_name=raster_name,
        )

    np.savetxt(out_dir / get_output_filename("x.grd"), XA, fmt="%.6f", delimiter=" ")
    np.savetxt(out_dir / get_output_filename("y.grd"), YA, fmt="%.6f", delimiter=" ")
    with (out_dir / get_output_filename("z.grd")).open("w", encoding="utf-8") as fz:
        for row in ZA:
            fz.write("\t".join("nan" if np.isnan(v) else f"{v:.6f}" for v in row) + "\n")
    log_func(f"{get_output_filename('x.grd')}, {get_output_filename('y.grd')}, {get_output_filename('z.grd')} written.")

    if custom_grid_definitions:
        from SCOPE.processing.custom_grid import create_custom_grids
        create_custom_grids(XA, YA, origin_x, origin_y, out_dir, log_func,
                            custom_grid_definitions, coord_system, output_prefix=output_prefix)
        if show_custom_grid_preview:
            for defn in custom_grid_definitions:
                if defn.enabled and defn.show_preview:
                    grid_path = out_dir / get_output_filename(defn.sanitized_filename())
                    plot_custom_grid_preview(XA, YA, grid_path, log_func, ang_deg=ang_deg, raster_name=raster_name)
    else:
        log_func("No custom grid files defined.")

    if threshold_layers:
        log_func("Creating threshold mask grid for AeoLiS...")
        create_threshold_mask_grid(XA, YA, origin_x, origin_y, out_dir, log_func, threshold_layers,
                                   coord_system, threshold_default_value,
                                   out_name=get_output_filename("threshold_mask.grd"))
    else:
        log_func("No threshold mask layers provided. Skipping threshold_mask.grd creation.")
