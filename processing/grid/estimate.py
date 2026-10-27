"""
Size estimates for a processing run, used to warn before very large runs.

All numbers are approximate. They are meant to catch runs that cannot finish
on the user's machine, not to predict exact sizes.
"""
import math
from dataclasses import dataclass

from .stream import NODES_PER_BLOCK

# Raster data is extracted this far beyond the model area so interpolation
# near its edges has support.
DATA_BUFFER = 50.0

# Memory per input sample: XYZ array, Delaunay triangulation and KD-tree.
BYTES_PER_SAMPLE = 300
# Working memory per node of one block during interpolation and writing.
BYTES_PER_BLOCK_NODE = 100
# Size of one line of the clipped XYZ text file.
XYZ_CHARS_PER_SAMPLE = 40
# Point-in-polygon throughput of the custom grid routine on one core.
NODE_CHECKS_PER_SECOND = 1e5

WARN_NODES = 50_000_000
WARN_DISK_FRACTION = 0.8
WARN_RAM_FRACTION = 0.7
WARN_SECONDS = 3600


@dataclass
class RunEstimate:
    """Estimated size of processing one raster over one model area."""
    nx: int
    ny: int
    nx_is_upper_bound: bool
    samples: int
    ram_bytes: int
    disk_bytes: int
    node_checks: int

    @property
    def nodes(self):
        return self.nx * self.ny

    @property
    def seconds(self):
        """Rough run time of the custom grids and threshold mask."""
        return self.node_checks / NODE_CHECKS_PER_SECOND


def grid_shape(width, height, dx, dy, min_cell_size=None):
    """
    Number of grid nodes (nx, ny, nx_is_upper_bound).

    Uniform grids (``min_cell_size`` None) are exact. For adaptive grids the
    cross-shore layout depends on the data, so nx is the upper bound reached
    when the whole width uses ``min_cell_size``.
    """
    ny = int(math.ceil(height / dy)) + 1
    if min_cell_size is None:
        return int(math.ceil(width / dx)) + 1, ny, False
    return int(math.ceil(width / min_cell_size)) + 2, ny, True


def _chars(text):
    """Characters one written value takes, including its separator."""
    return len(text) + 1


def estimate_run(width, height, dx, dy, pixel_area, max_abs_coord,
                 min_cell_size=None, raster_area=None, custom_grids=(), threshold_layers=0):
    """
    Estimate nodes, memory and disk use for one raster over one model area.

    Args:
        width, height: Model area size in working CRS units
        dx, dy: Grid spacing; dy is the longshore spacing for adaptive grids
        pixel_area: Area of one raster pixel in working CRS units
        max_abs_coord: Largest absolute output coordinate, which sets the
            width of the values in x.grd and y.grd
        min_cell_size: Minimum cross-shore spacing of an adaptive grid, or None
        raster_area: Raster extent area, caps the number of samples
        custom_grids: (decimals, layer_count) per enabled custom grid
        threshold_layers: Number of threshold mask layers, 0 for no mask

    Returns:
        RunEstimate
    """
    nx, ny, upper = grid_shape(width, height, dx, dy, min_cell_size)
    nodes = nx * ny

    sample_area = (width + 2 * DATA_BUFFER) * (height + 2 * DATA_BUFFER)
    if raster_area is not None:
        sample_area = min(sample_area, raster_area)
    samples = int(sample_area / pixel_area) if pixel_area > 0 else 0

    chars_per_node = 2 * _chars(f"{-abs(max_abs_coord):.6f}") + _chars(f"{-99.0:.6f}")
    node_checks = 0
    for decimals, layer_count in custom_grids:
        chars_per_node += _chars("10") if decimals == 0 else _chars(f"{-10.0:.{decimals}f}")
        node_checks += nodes * layer_count
    if threshold_layers:
        chars_per_node += _chars(f"({-1.0:.18e}{-1.0:+.18e}j)")
        node_checks += nodes * threshold_layers

    return RunEstimate(
        nx=nx,
        ny=ny,
        nx_is_upper_bound=upper,
        samples=samples,
        ram_bytes=samples * BYTES_PER_SAMPLE + min(nodes, NODES_PER_BLOCK) * BYTES_PER_BLOCK_NODE,
        disk_bytes=nodes * chars_per_node + samples * XYZ_CHARS_PER_SAMPLE,
        node_checks=node_checks,
    )


def format_bytes(n):
    """Human-readable size with binary units, e.g. '1.5 GB'."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _format_count(n):
    if n >= 1e9:
        return f"{n / 1e9:.1f} billion"
    if n >= 1e6:
        return f"{n / 1e6:.1f} million"
    return f"{n:,}"


def _format_seconds(s):
    if s >= 3600:
        return f"{s / 3600:.1f} h"
    if s >= 60:
        return f"{s / 60:.0f} min"
    return f"{s:.0f} s"


def _largest(estimates):
    return max(estimates, key=lambda e: e.nodes)


def summary(estimates):
    """One-line summary of a run made of one or more estimates, for the log."""
    largest = _largest(estimates)
    bound = "up to " if largest.nx_is_upper_bound else ""
    text = (
        f"Size estimate: {bound}{largest.nx:,} × {largest.ny:,} nodes per grid, "
        f"~{format_bytes(sum(e.disk_bytes for e in estimates))} of files, "
        f"~{format_bytes(max(e.ram_bytes for e in estimates))} peak memory"
    )
    seconds = sum(e.seconds for e in estimates)
    if seconds >= 1:
        text += f", ~{_format_seconds(seconds)} for custom grids and threshold mask"
    return text


def check_run(estimates, free_disk=None, available_ram=None):
    """
    Return the reasons to warn about a run, or an empty list.

    Rasters and sub-areas are processed one after another, so memory is the
    largest single estimate while disk use and run time add up.

    Args:
        estimates: RunEstimate per raster and sub-area
        free_disk: Free bytes on the output drive, or None if unknown
        available_ram: Available bytes of memory, or None if unknown
    """
    reasons = []
    largest = _largest(estimates)
    if largest.nodes > WARN_NODES:
        bound = "up to " if largest.nx_is_upper_bound else ""
        reasons.append(
            f"Grid of {bound}{largest.nx:,} × {largest.ny:,} nodes ({_format_count(largest.nodes)})"
        )

    disk = sum(e.disk_bytes for e in estimates)
    if free_disk is not None and disk > WARN_DISK_FRACTION * free_disk:
        reasons.append(
            f"About {format_bytes(disk)} of output files, {format_bytes(free_disk)} free on the output drive"
        )

    ram = max(e.ram_bytes for e in estimates)
    if available_ram is not None and ram > WARN_RAM_FRACTION * available_ram:
        reasons.append(
            f"About {format_bytes(ram)} of memory for {_format_count(max(e.samples for e in estimates))} "
            f"input samples, {format_bytes(available_ram)} available"
        )

    seconds = sum(e.seconds for e in estimates)
    if seconds > WARN_SECONDS:
        reasons.append(f"Custom grids and threshold mask take roughly {_format_seconds(seconds)}")
    return reasons
