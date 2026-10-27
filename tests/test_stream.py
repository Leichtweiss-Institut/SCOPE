"""
Tests that block-wise grid processing matches processing the whole grid at once.
"""
import io

import numpy as np
import pytest

from scope.processing.grid.gridmath import node_coordinates, uniform_axes
from scope.processing.grid.stream import (
    GridBounds,
    GridInterpolator,
    NodeGrid,
    PreviewSampler,
    rows_per_block,
    write_bed_rows,
    write_coordinate_rows,
)

griddata = pytest.importorskip("scipy.interpolate").griddata

ANG = 30.0
LL = (1000.0, 2000.0)
CENTRE = (1100.0, 2060.0)
ORIGIN = (995.5, 1990.25)


def make_grid(origin=ORIGIN):
    x, y = uniform_axes(200.0, 130.0, 1.0, 1.0)
    return NodeGrid(x, y, *LL, ANG, *CENTRE, origin=origin)


def full_grid(grid):
    """Reference: the whole grid as one array, as the pipeline built it before."""
    XG, YG = node_coordinates(grid.x_axis, grid.y_axis, grid.ll_x, grid.ll_y,
                              grid.ang_deg, grid.ox, grid.oy)
    if grid.origin is None:
        return XG, YG, XG, YG
    return XG, YG, XG - grid.origin[0], YG - grid.origin[1]


def raster_samples():
    """1 m raster around the grid that covers only part of it, so some nodes need the nearest fill."""
    rng = np.random.default_rng(0)
    X, Y = np.meshgrid(np.arange(980.5, 1180.0), np.arange(1960.5, 2160.0))
    return np.column_stack([X.ravel(), Y.ravel()]), rng.random(X.size) * 10 - 5


def full_bed(XG, YG, pts_xy, pts_z):
    """Reference: the pipeline's former griddata linear + nearest fill."""
    grid_coords = np.column_stack([XG.ravel(), YG.ravel()])
    ZA = griddata(pts_xy, pts_z, grid_coords, method="linear", fill_value=np.nan).reshape(XG.shape)
    nan_mask = np.isnan(ZA)
    nearest = griddata(pts_xy, pts_z, grid_coords, method="nearest")
    ZA[nan_mask] = nearest.reshape(XG.shape)[nan_mask]
    return ZA


# Block sizes: one row, a few rows that do not divide ny, and the whole grid.
BLOCK_SIZES = [1, 7 * 201, 10**9]


def test_rows_per_block():
    assert rows_per_block(1000, 2_000_000) == 2000
    assert rows_per_block(3_000_000, 2_000_000) == 1
    assert rows_per_block(0, 10) == 10


@pytest.mark.parametrize("nodes_per_block", BLOCK_SIZES)
@pytest.mark.parametrize("origin", [ORIGIN, None])
def test_blocks_match_full_grid(nodes_per_block, origin):
    grid = make_grid(origin)
    blocks = list(grid.blocks(nodes_per_block))
    assert [b[0] for b in blocks] == list(range(0, grid.shape[0], rows_per_block(grid.shape[1], nodes_per_block)))
    for streamed, full in zip(zip(*[b[1:] for b in blocks]), full_grid(grid)):
        assert np.array_equal(np.concatenate(streamed), full)


@pytest.mark.parametrize("nodes_per_block", BLOCK_SIZES)
def test_interpolation_matches_griddata(nodes_per_block):
    grid = make_grid()
    pts_xy, pts_z = raster_samples()
    interp = GridInterpolator(pts_xy, pts_z)
    parts, filled = [], 0
    for _, XG, YG, _, _ in grid.blocks(nodes_per_block):
        values, n = interp(XG, YG)
        parts.append(values)
        filled += n
    XG, YG, _, _ = full_grid(grid)
    expected = full_bed(XG, YG, pts_xy, pts_z)
    assert filled > 0
    assert np.array_equal(np.concatenate(parts), expected)


def test_interpolation_without_scipy_uses_nearest():
    pts_xy = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]])
    pts_z = np.array([1.0, 2.0, 3.0])
    interp = GridInterpolator(pts_xy, pts_z)
    interp.uses_scipy = False
    values, filled = interp(np.array([[1.0, 9.0]]), np.array([[1.0, 1.0]]))
    assert values.tolist() == [[1.0, 2.0]] and filled == 0


@pytest.mark.parametrize("nodes_per_block", BLOCK_SIZES)
def test_streamed_files_match_full_writers(tmp_path, nodes_per_block):
    grid = make_grid()
    pts_xy, pts_z = raster_samples()
    interp = GridInterpolator(pts_xy, pts_z)
    with (tmp_path / "x.grd").open("wt") as fx, \
            (tmp_path / "z.grd").open("w", encoding="utf-8") as fz:
        for _, XG, YG, XA, _ in grid.blocks(nodes_per_block):
            write_coordinate_rows(fx, XA)
            write_bed_rows(fz, interp(XG, YG)[0])

    XG, YG, XA, _ = full_grid(grid)
    ZA = full_bed(XG, YG, pts_xy, pts_z)
    np.savetxt(tmp_path / "x_ref.grd", XA, fmt="%.6f", delimiter=" ")
    with (tmp_path / "z_ref.grd").open("w", encoding="utf-8") as fz:
        for row in ZA:
            fz.write("\t".join("nan" if np.isnan(v) else f"{v:.6f}" for v in row) + "\n")

    assert (tmp_path / "x.grd").read_bytes() == (tmp_path / "x_ref.grd").read_bytes()
    assert (tmp_path / "z.grd").read_bytes() == (tmp_path / "z_ref.grd").read_bytes()


def test_bed_rows_write_nan():
    out = io.StringIO()
    write_bed_rows(out, np.array([[np.nan, 1.5], [-2.25, np.nan]]))
    assert out.getvalue() == "nan\t1.500000\n-2.250000\tnan\n"


def test_bounds_match_full_grid():
    grid = make_grid()
    bounds = GridBounds()
    for _, _, _, XA, YA in grid.blocks(7 * 201):
        bounds.update(XA, YA)
    _, _, XA, YA = full_grid(grid)
    assert (bounds.x_min, bounds.x_max, bounds.y_min, bounds.y_max) == (
        XA.min(), XA.max(), YA.min(), YA.max())


def test_spacing_summary_matches_node_distances():
    x = np.array([0.0, 20.0, 35.0, 45.0, 50.0, 55.0])
    y = np.array([0.0, 2.0, 4.0, 7.0])
    grid = NodeGrid(x, y, *LL, ANG, *CENTRE)
    _, _, XA, YA = full_grid(grid)
    dx = np.hypot(np.diff(XA, axis=1), np.diff(YA, axis=1))
    dy = np.hypot(np.diff(XA, axis=0), np.diff(YA, axis=0))
    np.testing.assert_allclose(grid.spacing_summary(), (dx.min(), dx.max(), dy.min(), dy.max()))


@pytest.mark.parametrize("max_nodes", [1000, 40])
def test_preview_sampler_matches_strided_full_grid(max_nodes):
    grid = make_grid()
    sampler = PreviewSampler(grid.shape, max_nodes=max_nodes)
    for row_start, _, _, XA, YA in grid.blocks(7 * 201):
        sampler.add(row_start, XA, YA)
    XS, YS = sampler.arrays()
    _, _, XA, YA = full_grid(grid)
    assert sampler.is_full == (max_nodes == 1000)
    assert np.array_equal(XS, XA[::sampler.row_step, ::sampler.col_step])
    assert np.array_equal(YS, YA[::sampler.row_step, ::sampler.col_step])
