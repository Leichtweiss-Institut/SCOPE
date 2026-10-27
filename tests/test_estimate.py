"""
Tests for the run size estimates behind the large-run warning.
"""
import numpy as np
import pytest

from scope.processing.grid.estimate import (
    WARN_NODES,
    check_run,
    estimate_run,
    format_bytes,
    grid_shape,
    summary,
)
from scope.processing.grid.gridmath import uniform_axes
from scope.processing.grid.stream import GridInterpolator, NodeGrid, write_bed_rows, write_coordinate_rows
from scope.processing.grid.threshold import (
    create_left_to_right_adaptive_grid,
    create_threshold_based_adaptive_grid,
)

NO_SAMPLES = 1e30  # pixel area so large that no samples are counted


@pytest.mark.parametrize("w, h, dx, dy", [(100.0, 45.0, 10.0, 10.0), (3000.0, 2000.0, 5.0, 2.5),
                                          (10.0, 10.0, 3.0, 7.0)])
def test_uniform_shape_matches_axes(w, h, dx, dy):
    x, y = uniform_axes(w, h, dx, dy)
    assert grid_shape(w, h, dx, dy) == (len(x), len(y), False)


@pytest.mark.parametrize("crossing", [0.0, 0.1, 400.0, 999.0, 1000.0])
@pytest.mark.parametrize("factor", [1.01, 1.2, 2.0])
def test_adaptive_shape_is_upper_bound(crossing, factor):
    w, h, dy, min_dx, max_dx = 1000.0, 300.0, 5.0, 1.3, 50.0
    nx, ny, upper = grid_shape(w, h, None, dy, min_dx)
    x, y = create_threshold_based_adaptive_grid(w, h, dy, min_dx, max_dx, crossing, factor)
    x_lr, _ = create_left_to_right_adaptive_grid(w, h, dy, min_dx, max_dx)
    assert upper and ny == len(y)
    assert len(x) <= nx and len(x_lr) <= nx


@pytest.mark.parametrize("origin", [(470000.0, 6019000.0), None])
def test_disk_estimate_close_to_written_files(tmp_path, origin):
    w, h, dx, dy, ang = 600.0, 400.0, 2.0, 2.0, 23.0
    ll = (471000.0, 6018500.0)
    x, y = uniform_axes(w, h, dx, dy)
    grid = NodeGrid(x, y, *ll, ang, ll[0] + w / 2, ll[1] + h / 2, origin=origin)
    pts = np.array([[ll[0] - 500, ll[1] - 500], [ll[0] + 1500, ll[1] - 500], [ll[0], ll[1] + 1500]])
    interp = GridInterpolator(pts, np.array([-12.5, 3.25, 8.0]))
    with (tmp_path / "x.grd").open("wt") as fx, (tmp_path / "y.grd").open("wt") as fy, \
            (tmp_path / "z.grd").open("w") as fz:
        for _, XG, YG, XA, YA in grid.blocks():
            write_coordinate_rows(fx, XA)
            write_coordinate_rows(fy, YA)
            write_bed_rows(fz, interp(XG, YG)[0])
    written = sum(p.stat().st_size for p in tmp_path.iterdir())

    max_abs = np.hypot(w, h) if origin else max(ll) + np.hypot(w, h)
    est = estimate_run(w, h, dx, dy, NO_SAMPLES, max_abs)
    assert est.samples == 0
    assert 0.8 * written <= est.disk_bytes <= 1.25 * written


def test_samples_capped_by_raster_area():
    est = estimate_run(1000.0, 1000.0, 10.0, 10.0, 1.0, 1000.0, raster_area=500_000.0)
    assert est.samples == 500_000
    est = estimate_run(1000.0, 1000.0, 10.0, 10.0, 1.0, 1000.0)
    assert est.samples == 1100 * 1100


def test_custom_grids_and_mask_add_size_and_time():
    base = estimate_run(1000.0, 1000.0, 1.0, 1.0, NO_SAMPLES, 1500.0)
    more = estimate_run(1000.0, 1000.0, 1.0, 1.0, NO_SAMPLES, 1500.0,
                        custom_grids=[(3, 4), (0, 1)], threshold_layers=2)
    assert more.disk_bytes > base.disk_bytes
    assert base.node_checks == 0 and more.node_checks == base.nodes * 7


def test_small_run_has_no_warnings():
    est = estimate_run(3000.0, 2000.0, 5.0, 5.0, 1.0, 4000.0)
    assert check_run([est], free_disk=500 * 1024**3, available_ram=16 * 1024**3) == []


def test_reported_case_warns_about_nodes_disk_and_ram():
    # 10 km × 10 km at 0.1 m over a 1 m raster, as in the bug report.
    est = estimate_run(10_000.0, 10_000.0, 0.1, 0.1, 1.0, 15_000.0)
    assert (est.nx, est.ny) == (100_001, 100_001) and est.nodes > WARN_NODES
    reasons = check_run([est], free_disk=200 * 1024**3, available_ram=16 * 1024**3)
    assert len(reasons) == 3
    assert reasons[0].startswith("Grid of 100,001 × 100,001 nodes (10.0 billion)")


def test_unknown_disk_and_ram_are_skipped():
    est = estimate_run(10_000.0, 10_000.0, 0.1, 0.1, 1.0, 15_000.0)
    assert len(check_run([est])) == 1


def test_several_areas_add_disk_but_not_memory():
    est = estimate_run(2000.0, 2000.0, 1.0, 1.0, 1.0, 3000.0)
    free, ram = 1.5 * est.disk_bytes, 2 * est.ram_bytes
    assert check_run([est], free_disk=free, available_ram=ram) == []
    reasons = check_run([est, est], free_disk=free, available_ram=ram)
    assert len(reasons) == 1 and "output files" in reasons[0]


def test_long_custom_grid_run_warns():
    # 100 million nodes against four layers: about an hour at 10^5 node checks per second.
    est = estimate_run(10_000.0, 10_000.0, 1.0, 1.0, NO_SAMPLES, 15_000.0, custom_grids=[(3, 4)])
    assert any("roughly" in r for r in check_run([est]))


def test_summary_marks_adaptive_upper_bound():
    est = estimate_run(1000.0, 500.0, None, 2.0, 1.0, 1200.0, min_cell_size=1.0)
    assert summary([est]).startswith("Size estimate: up to 1,002 × 251 nodes")


@pytest.mark.parametrize("n, text", [(512, "512 B"), (1536, "1.5 KB"), (3 * 1024**3, "3.0 GB"),
                                     (2 * 1024**4, "2.0 TB")])
def test_format_bytes(n, text):
    assert format_bytes(n) == text
