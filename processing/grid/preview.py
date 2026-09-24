"""
Matplotlib preview panes for generated grids.
"""
from pathlib import Path

import numpy as np


def _to_extent_coordinates(XA, YA, ang_deg=0.0):
    """Shift coordinates and undo grid rotation so axes align with model x/y directions."""
    x0 = float(XA[0, 0])
    y0 = float(YA[0, 0])
    XP = XA - x0
    YP = YA - y0

    # Rotate into model-aligned frame (cross-shore = x-axis, longshore = y-axis).
    if abs(float(ang_deg)) < 1e-12:
        return XP, YP

    theta = np.radians(-float(ang_deg))
    c, s = np.cos(theta), np.sin(theta)
    XR = c * XP - s * YP
    YR = s * XP + c * YP
    return XR, YR


def _preview_title_suffix(raster_name):
    """Return ' (raster name)' for preview titles, or '' when unnamed."""
    return f" ({raster_name})" if raster_name else ""


# Font sizes and padding shared by all preview panes.
_TITLE_FS = 15
_LABEL_FS = 13
_TICK_FS = 11
_CBAR_LABEL_FS = 13
_CBAR_TICK_FS = 11
_LABELPAD = 12
_CBAR_LABELPAD = 14


_MPL_DEFAULTS_CONFIGURED = False


def _configure_matplotlib_defaults():
    """Use Arial with embedded TrueType fonts and 1000 DPI exports, once per session."""
    global _MPL_DEFAULTS_CONFIGURED
    if _MPL_DEFAULTS_CONFIGURED:
        return

    import matplotlib
    import matplotlib.font_manager as fm

    # Arial is often installed system-wide but missing from matplotlib's font cache.
    for font_path in fm.findSystemFonts():
        if "arial" in Path(font_path).stem.lower():
            fm.fontManager.addfont(font_path)

    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = ["Arial", "Liberation Sans", "DejaVu Sans"]
    # Embed TrueType fonts in PDF/EPS exports instead of Type 3 bitmaps.
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    matplotlib.rcParams["savefig.dpi"] = 1000

    _MPL_DEFAULTS_CONFIGURED = True


def _add_matched_colorbar(fig, ax, mesh, label):
    """Attach a colorbar whose vertical extent matches the axes height.

    ``fig.colorbar(..., shrink=...)`` does not track the true height of an
    equal-aspect axes, so it tends to end up taller or shorter than the plot.
    Using an appended axes of the same height fixes that for the 2D panes.
    """
    from mpl_toolkits.axes_grid1 import make_axes_locatable

    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="4%", pad=0.25)
    cbar = fig.colorbar(mesh, cax=cax)
    cbar.set_label(label, fontsize=_CBAR_LABEL_FS, labelpad=_CBAR_LABELPAD)
    cbar.ax.tick_params(labelsize=_CBAR_TICK_FS)
    return cbar


def plot_custom_grid_preview(XA, YA, grid_path, log_func, ang_deg=0.0, raster_name=None):
    """Show a preview pane for one custom grid file if it exists."""
    if not grid_path.is_file():
        log_func(f"Custom grid preview skipped: {grid_path.name} not found.")
        return

    try:
        import matplotlib.pyplot as plt
        _configure_matplotlib_defaults()
        values = np.loadtxt(grid_path, dtype=float)
        XP, YP = _to_extent_coordinates(XA, YA, ang_deg)

        expected_cell_shape = (XA.shape[0] - 1, XA.shape[1] - 1)
        expected_node_shape = XA.shape

        if values.shape == expected_cell_shape:
            values_plot = values
        elif values.shape == expected_node_shape:
            # Custom grids are written node-based; convert to cell values for preview.
            values_plot = values[:-1, :-1]
            log_func(
                f"Custom grid preview: converted node-shaped grid {values.shape} to cell view {values_plot.shape}."
            )
        else:
            log_func(
                f"Custom grid preview skipped: shape mismatch {values.shape} vs expected {expected_cell_shape} or {expected_node_shape}"
            )
            return

        fig, ax = plt.subplots(figsize=(9, 6))
        mesh = ax.pcolormesh(XP, YP, values_plot, cmap="viridis", shading="auto")
        _add_matched_colorbar(fig, ax, mesh, "Value")
        ax.set_title(f"{grid_path.name}{_preview_title_suffix(raster_name)}", fontsize=_TITLE_FS)
        ax.set_xlabel("X extent (m)", fontsize=_LABEL_FS, labelpad=_LABELPAD)
        ax.set_ylabel("Y extent (m)", fontsize=_LABEL_FS, labelpad=_LABELPAD)
        ax.tick_params(axis="both", labelsize=_TICK_FS)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, alpha=0.2)
        plt.tight_layout()
        plt.show(block=False)
        log_func(f"Opened custom grid preview window for {grid_path.name}.")
    except Exception as e:
        log_func(f"Custom grid preview failed for {grid_path.name}: {e}")


def plot_grid_preview(XA, YA, ZA, log_func, title="Grid Preview", max_lines=180,
                       show_spacing=True, show_bed_2d=True, show_3d_preview=True, ang_deg=0.0,
                       raster_name=None):
    """Show matplotlib previews for grid spacing and bed level terrain.

    Each preview is gated by its own flag so the caller can open any subset:
    ``show_spacing`` (cross-shore Δx map), ``show_bed_2d`` (2D terrain) and
    ``show_3d_preview`` (3D terrain).
    """
    try:
        import matplotlib.pyplot as plt
        _configure_matplotlib_defaults()
    except Exception as e:
        log_func(f"Grid preview skipped: matplotlib unavailable ({e})")
        return

    try:
        suffix = _preview_title_suffix(raster_name)
        XP, YP = _to_extent_coordinates(XA, YA, ang_deg)
        ny, nx = XA.shape
        row_step = max(1, ny // max_lines)
        col_step = max(1, nx // max_lines)

        if show_spacing:
            fig, ax = plt.subplots(figsize=(9, 6))

            # Cross-shore spacing per edge and cell-centered value for colormapping.
            dx_edges = np.hypot(np.diff(XA, axis=1), np.diff(YA, axis=1))  # (ny, nx-1)
            dx_cells = 0.5 * (dx_edges[:-1, :] + dx_edges[1:, :])  # (ny-1, nx-1)

            # On uniform grids Δx differs only by rounding noise; widen the colour
            # range so that noise does not show up as a chessboard pattern.
            dmin = float(np.nanmin(dx_cells))
            dmax = float(np.nanmax(dx_cells))
            if (dmax - dmin) <= 1e-6 * max(abs(dmax), 1.0):
                mid = 0.5 * (dmin + dmax)
                vmin, vmax = mid - 1.0, mid + 1.0
            else:
                vmin, vmax = dmin, dmax

            mesh = ax.pcolormesh(
                XP,
                YP,
                dx_cells,
                cmap="plasma_r",
                shading="auto",
                alpha=0.9,
                vmin=vmin,
                vmax=vmax,
            )
            _add_matched_colorbar(fig, ax, mesh, "Cross-shore cell size Δx (m)")

            # Overlay a thinned grid for visual structure.
            for ri in range(0, ny, row_step):
                ax.plot(XP[ri, :], YP[ri, :], color="black", linewidth=0.25, alpha=0.4)
            for cj in range(0, nx, col_step):
                ax.plot(XP[:, cj], YP[:, cj], color="black", linewidth=0.25, alpha=0.4)

            ax.set_title(f"{title}{suffix}", fontsize=_TITLE_FS)
            ax.set_xlabel("X extent (m)", fontsize=_LABEL_FS, labelpad=_LABELPAD)
            ax.set_ylabel("Y extent (m)", fontsize=_LABEL_FS, labelpad=_LABELPAD)
            ax.tick_params(axis="both", labelsize=_TICK_FS)
            ax.set_aspect("equal", adjustable="box")
            ax.grid(True, alpha=0.25)
            plt.tight_layout()
            plt.show(block=False)
            log_func("Opened grid spacing preview window.")

        if show_bed_2d:
            # Separate 2D bed-level terrain preview.
            fig2, ax2d = plt.subplots(figsize=(9, 6))

            bed = np.array(ZA, dtype=float)
            bed_mesh = ax2d.pcolormesh(XP, YP, bed[:-1, :-1], cmap="terrain", shading="auto")
            _add_matched_colorbar(fig2, ax2d, bed_mesh, "Bed level z (m)")
            ax2d.set_title(f"Bed Level Preview (Terrain){suffix}", fontsize=_TITLE_FS)
            ax2d.set_xlabel("X extent (m)", fontsize=_LABEL_FS, labelpad=_LABELPAD)
            ax2d.set_ylabel("Y extent (m)", fontsize=_LABEL_FS, labelpad=_LABELPAD)
            ax2d.tick_params(axis="both", labelsize=_TICK_FS)
            ax2d.set_aspect("equal", adjustable="box")
            ax2d.grid(True, alpha=0.2)
            plt.tight_layout()
            plt.show(block=False)
            log_func("Opened bed level preview window (2D terrain).")

        if show_3d_preview:
            # Separate 3D bed-level terrain preview.
            fig3 = plt.figure(figsize=(8.5, 5.8))
            ax3d = fig3.add_subplot(1, 1, 1, projection="3d")

            # Decimate for large grids to keep 3D rendering responsive.
            stride_y = max(1, XA.shape[0] // 180)
            stride_x = max(1, XA.shape[1] // 180)
            X3 = XP[::stride_y, ::stride_x]
            Y3 = YP[::stride_y, ::stride_x]
            Z3 = ZA[::stride_y, ::stride_x]

            # Exaggerate relief; surface and colormap share the scaled values.
            Z_EXAG = 10.0
            Z3e = Z3 * Z_EXAG

            surf = ax3d.plot_surface(
                X3,
                Y3,
                Z3e,
                cmap="terrain",
                linewidth=0,
                antialiased=True,
                alpha=0.95,
            )
            cbar3 = fig3.colorbar(surf, ax=ax3d, shrink=0.6, pad=0.1,
                                   label=f"Bed level z (m, ×{int(Z_EXAG)} exaggeration)")
            cbar3.set_label(
                f"Bed level z (m, ×{int(Z_EXAG)} exaggeration)",
                fontsize=_CBAR_LABEL_FS, labelpad=_CBAR_LABELPAD,
            )
            cbar3.ax.tick_params(labelsize=_CBAR_TICK_FS)
            ax3d.set_title(f"Bed Level Preview (3D){suffix}", fontsize=_TITLE_FS)
            ax3d.set_xlabel("X extent (m)", fontsize=_LABEL_FS, labelpad=22)
            ax3d.set_ylabel("Y extent (m)", fontsize=_LABEL_FS, labelpad=22)
            ax3d.set_zlabel(f"Z (m, ×{int(Z_EXAG)})", fontsize=_LABEL_FS, labelpad=12)
            # Fewer ticks so labels do not overlap.
            from matplotlib.ticker import MaxNLocator
            ax3d.yaxis.set_major_locator(MaxNLocator(nbins=4, prune="both"))
            ax3d.zaxis.set_major_locator(MaxNLocator(nbins=5, prune="both"))
            ax3d.tick_params(axis="both", labelsize=_TICK_FS)
            ax3d.tick_params(axis="z", pad=6)
            ax3d.tick_params(axis="x", pad=4)
            ax3d.tick_params(axis="y", pad=4)

            xr = float(np.nanmax(XP) - np.nanmin(XP))
            yr = float(np.nanmax(YP) - np.nanmin(YP))
            zr = float((np.nanmax(ZA) - np.nanmin(ZA)) * Z_EXAG)
            hmax = max(xr, yr, 1e-9)
            # Keep realistic relative scale but avoid extreme flattening.
            z_aspect = max(zr, 0.02 * hmax)
            try:
                ax3d.set_box_aspect((max(xr, 1e-9), max(yr, 1e-9), z_aspect))
            except Exception:
                pass

            plt.tight_layout()
            plt.show(block=False)
            log_func("Opened bed level preview window (3D).")

    except Exception as e:
        log_func(f"Grid preview failed: {e}")
