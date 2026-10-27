"""
Block-wise grid processing without QGIS.

Grid nodes are produced, interpolated and written a block of rows at a time,
so memory use depends on the block size instead of the full grid size. Every
step works node by node, so the files are identical to processing the whole
grid at once.
"""
import math

import numpy as np

from .gridmath import node_rows

# About 200 MB of working arrays per block.
NODES_PER_BLOCK = 2_000_000

# Previews keep at most this many nodes along each axis.
PREVIEW_MAX_NODES = 1000


def rows_per_block(nx, nodes_per_block=NODES_PER_BLOCK):
    """Number of grid rows that fit in one block, at least one."""
    return max(1, nodes_per_block // max(nx, 1))


class NodeGrid:
    """
    Node layout of a rotated grid, produced a block of rows at a time.

    Args:
        x_axis, y_axis: Local node positions along x and y
        ll_x, ll_y: Unrotated lower-left corner
        ang_deg: Rotation angle in degrees
        ox, oy: Rotation centre
        origin: (x, y) subtracted from the world coordinates for local
            output, or None to write world coordinates
    """

    def __init__(self, x_axis, y_axis, ll_x, ll_y, ang_deg, ox, oy, origin=None):
        self.x_axis = np.asarray(x_axis, dtype=float)
        self.y_axis = np.asarray(y_axis, dtype=float)
        self.ll_x, self.ll_y = ll_x, ll_y
        self.ang_deg = ang_deg
        self.ox, self.oy = ox, oy
        self.origin = origin

    @property
    def shape(self):
        return len(self.y_axis), len(self.x_axis)

    def blocks(self, nodes_per_block=NODES_PER_BLOCK):
        """
        Yield ``(row_start, XG, YG, XA, YA)`` for consecutive blocks of rows.

        XG, YG are world coordinates (used for interpolation); XA, YA are the
        output coordinates, shifted by ``origin`` in local mode.
        """
        ny, nx = self.shape
        step = rows_per_block(nx, nodes_per_block)
        for row_start in range(0, ny, step):
            XG, YG = node_rows(self.x_axis, self.y_axis[row_start:row_start + step],
                               self.ll_x, self.ll_y, self.ang_deg, self.ox, self.oy)
            if self.origin is None:
                XA, YA = XG, YG
            else:
                XA, YA = XG - self.origin[0], YG - self.origin[1]
            yield row_start, XG, YG, XA, YA

    def spacing_summary(self):
        """
        Return (dx_min, dx_max, dy_min, dy_max) of the node spacing.

        Rotation preserves distances, so the spacing follows from the axes.
        """
        dx = np.diff(self.x_axis)
        dy = np.diff(self.y_axis)
        if dx.size == 0 or dy.size == 0:
            raise ValueError("grid needs at least two nodes along each axis")
        return float(dx.min()), float(dx.max()), float(dy.min()), float(dy.max())


class GridInterpolator:
    """
    Linear interpolation of XYZ samples, with nearest-neighbour fill outside
    their convex hull.

    Gives the same values as ``scipy.interpolate.griddata`` with
    ``method='linear'`` followed by a ``method='nearest'`` fill of the NaN
    nodes, but builds the triangulation once and can be called per block.
    Without scipy it falls back to a brute-force nearest-neighbour search.
    """

    def __init__(self, pts_xy, pts_z):
        self.pts_xy = pts_xy
        self.pts_z = pts_z
        self._nearest = None
        try:
            from scipy.interpolate import LinearNDInterpolator
        except ImportError:
            self.uses_scipy = False
            self._linear = None
        else:
            self.uses_scipy = True
            self._linear = LinearNDInterpolator(pts_xy, pts_z, fill_value=np.nan)

    def __call__(self, XG, YG):
        """
        Interpolate at the given node coordinates.

        Returns:
            tuple: (values with the shape of XG, number of nodes filled by
            nearest neighbour)
        """
        xi = np.column_stack([XG.ravel(), YG.ravel()])
        if not self.uses_scipy:
            return self._brute_force_nearest(xi).reshape(XG.shape), 0

        values = self._linear(xi)
        nan_mask = np.isnan(values)
        n_filled = int(np.count_nonzero(nan_mask))
        if n_filled:
            if self._nearest is None:
                from scipy.interpolate import NearestNDInterpolator
                self._nearest = NearestNDInterpolator(self.pts_xy, self.pts_z)
            values[nan_mask] = self._nearest(xi[nan_mask])
        return values.reshape(XG.shape), n_filled

    def _brute_force_nearest(self, xi):
        out = np.empty(len(xi))
        for k, (gx, gy) in enumerate(xi):
            dists = np.hypot(self.pts_xy[:, 0] - gx, self.pts_xy[:, 1] - gy)
            out[k] = self.pts_z[np.argmin(dists)]
        return out


def write_coordinate_rows(fh, block):
    """Append rows of x.grd or y.grd; same format as the full-grid np.savetxt."""
    np.savetxt(fh, block, fmt="%.6f", delimiter=" ")


def write_bed_rows(fh, block):
    """Append rows of z.grd: tab-separated, NaN written as 'nan'."""
    for row in block:
        fh.write("\t".join("nan" if np.isnan(v) else f"{v:.6f}" for v in row) + "\n")


class GridBounds:
    """Running min/max of the output coordinates over all blocks."""

    def __init__(self):
        self.x_min = self.y_min = math.inf
        self.x_max = self.y_max = -math.inf

    def update(self, XA, YA):
        self.x_min = min(self.x_min, float(XA.min()))
        self.x_max = max(self.x_max, float(XA.max()))
        self.y_min = min(self.y_min, float(YA.min()))
        self.y_max = max(self.y_max, float(YA.max()))


class PreviewSampler:
    """
    Keep every k-th row and column of one or more node arrays while blocks
    stream past. Grids up to ``max_nodes`` per axis are kept in full.
    """

    def __init__(self, shape, max_nodes=PREVIEW_MAX_NODES):
        ny, nx = shape
        self.row_step = max(1, math.ceil(ny / max_nodes))
        self.col_step = max(1, math.ceil(nx / max_nodes))
        self._parts = []

    @property
    def is_full(self):
        """True when nothing is dropped, so the samples equal the full grid."""
        return self.row_step == 1 and self.col_step == 1

    def add(self, row_start, *blocks):
        """Store the sampled rows and columns of each block, which share rows."""
        first = (-row_start) % self.row_step
        # Copies, so the samples do not keep the whole block alive.
        self._parts.append(tuple(b[first::self.row_step, ::self.col_step].copy() for b in blocks))

    def arrays(self):
        """Return the sampled arrays, one per block argument passed to ``add``."""
        if not self._parts:
            return ()
        return tuple(np.concatenate(cols, axis=0) for cols in zip(*self._parts))
