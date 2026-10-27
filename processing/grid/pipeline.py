"""
Grid generation pipeline: interpolation, adaptive spacing and output files.
"""
import math
from pathlib import Path

import numpy as np

from ...utils.constants import get_working_crs, NODATA_VAL
from ..progress import NullProgress
from ..custom_grid import create_threshold_mask_grid
from .gridmath import rot_point, to_local_frame, uniform_axes
from .preview import plot_custom_grid_preview, plot_grid_preview
from .stream import (
    GridBounds,
    GridInterpolator,
    NodeGrid,
    PreviewSampler,
    rows_per_block,
    write_bed_rows,
    write_coordinate_rows,
)
from .threshold import (
    create_left_to_right_adaptive_grid,
    create_threshold_based_adaptive_grid,
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
                     raster_name=None, progress=None):
    """
    Build a grid over the model area and write all enabled output files.

    Interpolates the XYZ samples onto a uniform or adaptive node layout and
    writes x.grd, y.grd and z.grd a block of rows at a time, so memory use does
    not grow with the grid size. Then writes any custom grids and the
    threshold mask.

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
        progress: Progress reporter (see processing.progress), or None
    """
    log_func("Creating SCOPE grids...")
    progress = progress or NullProgress()

    def get_output_filename(base_name):
        if output_prefix:
            return f"{output_prefix}_{base_name}"
        return base_name

    try:
        progress.start("Reading XYZ samples")
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
            local_x, local_y = to_local_frame(
                pts_xy[:, 0], pts_xy[:, 1], ang_deg,
                rot_center_x, rot_center_y, actual_ll_x, actual_ll_y,
            )

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
        grid_x, grid_y = uniform_axes(w, h, dx, dy)
        nx = len(grid_x)
        ny = len(grid_y)
        log_func(f"Creating uniform grid with {nx}x{ny} cells.")

    origin = (origin_x, origin_y) if coord_system == "local" else None
    grid = NodeGrid(grid_x, grid_y, actual_ll_x, actual_ll_y, ang_deg,
                    rot_center_x, rot_center_y, origin=origin)

    progress.start("Triangulating samples")
    interp = GridInterpolator(pts_xy, pts_z)
    if interp.uses_scipy:
        log_func("Using scipy linear interpolation (triangulation-based)...")
    else:
        log_func("Scipy not available, using nearest neighbor fallback...")

    if coord_system == "local":
        log_func("Converted coordinates to local system using lower-left as origin.")
    else:
        log_func(f"Using world coordinates ({get_working_crs().authid()}).")

    try:
        dx_min, dx_max, dy_min, dy_max = grid.spacing_summary()
        log_func(
            f"Grid spacing summary: Δx min/max = {dx_min:.3f}/{dx_max:.3f} m, Δy min/max = {dy_min:.3f}/{dy_max:.3f} m"
        )
    except Exception as e:
        log_func(f"Could not compute spacing summary: {e}")

    show_grid_preview = show_grid_spacing_preview or show_bed_2d_preview or show_bed_3d_preview
    show_custom_preview = show_custom_grid_preview and bool(custom_grid_definitions)
    sampler = PreviewSampler(grid.shape) if show_grid_preview or show_custom_preview else None
    bounds = GridBounds()
    n_blocks = math.ceil(ny / rows_per_block(nx))
    n_filled = 0

    x_name, y_name, z_name = (get_output_filename(n) for n in ("x.grd", "y.grd", "z.grd"))
    with (out_dir / x_name).open("wt") as fx, \
            (out_dir / y_name).open("wt") as fy, \
            (out_dir / z_name).open("w", encoding="utf-8") as fz:
        progress.start(f"Writing {x_name}, {y_name}, {z_name}", ny)
        for row_start, XG, YG, XA, YA in grid.blocks():
            ZA, filled = interp(XG, YG)
            n_filled += filled
            write_coordinate_rows(fx, XA)
            write_coordinate_rows(fy, YA)
            write_bed_rows(fz, ZA)
            bounds.update(XA, YA)
            if sampler is not None:
                sampler.add(row_start, XA, YA, ZA)
            progress.update(row_start + len(XA))
            if n_blocks > 1:
                log_func(f"Grid rows written: {row_start + len(XA):,}/{ny:,}")

    if n_filled:
        log_func(f"Filled {n_filled} NaN values with nearest neighbor.")
    log_func(f"{x_name}, {y_name}, {z_name} written.")

    if sampler is not None:
        XS, YS, ZS = sampler.arrays()
        if not sampler.is_full:
            log_func(f"Previews sample every {sampler.row_step} rows and {sampler.col_step} columns.")

    if show_grid_preview:
        dx_cells = None
        if not sampler.is_full:
            # Sampled nodes lie several cells apart; show the Δx of the cell
            # at each sampled column rather than the distance between samples.
            col_idx = np.arange(XS.shape[1] - 1) * sampler.col_step
            dx_cells = np.tile(np.diff(grid.x_axis)[col_idx], (XS.shape[0] - 1, 1))
        plot_grid_preview(
            XS,
            YS,
            ZS,
            log_func,
            title="Generated Grid Preview",
            show_spacing=show_grid_spacing_preview,
            show_bed_2d=show_bed_2d_preview,
            show_3d_preview=show_bed_3d_preview,
            ang_deg=ang_deg,
            raster_name=raster_name,
            dx_cells=dx_cells,
        )

    if custom_grid_definitions:
        from ..custom_grid import create_custom_grids

        preview_func = None
        if show_custom_preview:
            def preview_func(name, values):
                plot_custom_grid_preview(XS, YS, values, name, log_func,
                                         ang_deg=ang_deg, raster_name=raster_name)

        create_custom_grids(grid, bounds, origin_x, origin_y, out_dir, log_func,
                            custom_grid_definitions, coord_system, output_prefix=output_prefix,
                            preview_func=preview_func, progress=progress)
    else:
        log_func("No custom grid files defined.")

    if threshold_layers:
        log_func("Creating threshold mask grid for AeoLiS...")
        create_threshold_mask_grid(grid, bounds, origin_x, origin_y, out_dir, log_func, threshold_layers,
                                   coord_system, threshold_default_value,
                                   out_name=get_output_filename("threshold_mask.grd"),
                                   progress=progress)
    else:
        log_func("No threshold mask layers provided. Skipping threshold_mask.grd creation.")
