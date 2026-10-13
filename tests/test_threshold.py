"""
Tests for threshold crossing detection and the adaptive cross-shore layouts.
"""
import numpy as np
import pytest

from scope.processing.grid.threshold import (
    create_left_to_right_adaptive_grid,
    create_threshold_based_adaptive_grid,
    estimate_transition_factor,
    find_median_threshold_crossing,
)


def beach(width, height, step, crossing_of_y):
    """Regular samples whose elevation is 0 at x = crossing_of_y(y) and rises landward."""
    xs = np.arange(0.0, width + step / 2, step)
    ys = np.arange(step / 2, height, step)
    X, Y = np.meshgrid(xs, ys)
    Z = 0.05 * (X - crossing_of_y(Y))
    return X.ravel(), Y.ravel(), Z.ravel()


# --- find_median_threshold_crossing ---------------------------------------

def test_crossing_on_straight_shoreline():
    x, y, z = beach(200.0, 100.0, 1.0, lambda Y: np.full_like(Y, 120.0))
    crossing = find_median_threshold_crossing(x, y, z, 200.0, 100.0, 0.0, 10.0)
    # First sample strictly above 0 m lies one sample landward of x = 120 m.
    assert crossing == pytest.approx(121.0)


def test_crossing_is_median_over_rows():
    # Shoreline steps from 50 m to 150 m along y; 7 of 10 rows sit at 50 m.
    x, y, z = beach(200.0, 100.0, 1.0, lambda Y: np.where(Y < 70.0, 50.0, 150.0))
    crossing = find_median_threshold_crossing(x, y, z, 200.0, 100.0, 0.0, 10.0)
    assert crossing == pytest.approx(51.0)


def test_crossing_ignores_samples_outside_domain_and_nan():
    x, y, z = beach(200.0, 100.0, 1.0, lambda Y: np.full_like(Y, 120.0))
    # High samples outside the domain and NaN elevations must not count.
    x = np.concatenate([x, [-5.0, 10.0, 10.0]])
    y = np.concatenate([y, [50.0, 150.0, 50.0]])
    z = np.concatenate([z, [99.0, 99.0, np.nan]])
    crossing = find_median_threshold_crossing(x, y, z, 200.0, 100.0, 0.0, 10.0)
    assert crossing == pytest.approx(121.0)


def test_crossing_none_when_threshold_never_exceeded():
    x, y, z = beach(200.0, 100.0, 1.0, lambda Y: np.full_like(Y, 120.0))
    assert find_median_threshold_crossing(x, y, z, 200.0, 100.0, 100.0, 10.0) is None


def test_crossing_none_for_empty_input():
    empty = np.array([])
    assert find_median_threshold_crossing(empty, empty, empty, 100.0, 100.0, 0.0, 10.0) is None


# --- estimate_transition_factor -------------------------------------------

@pytest.mark.parametrize(
    "min_size, max_size, width",
    [(0.0, 10.0, 100.0), (5.0, 5.0, 100.0), (10.0, 5.0, 100.0), (1.0, 10.0, 0.0)],
)
def test_transition_factor_degenerate_inputs(min_size, max_size, width):
    assert estimate_transition_factor(min_size, max_size, width) == 1.0


def test_transition_factor_spans_size_ratio():
    min_size, max_size, width = 2.0, 20.0, 330.0
    factor = estimate_transition_factor(min_size, max_size, width)
    n_cells = round(width / (0.5 * (min_size + max_size)))
    assert factor > 1.0
    assert factor ** (n_cells - 1) == pytest.approx(max_size / min_size)


# --- adaptive layouts -----------------------------------------------------

def assert_valid_axis(x, width, max_cell):
    """Starts at 0, increases strictly, and ends within one cell of ``width``."""
    dx = np.diff(x)
    assert x[0] == 0.0
    assert np.all(dx > 0)
    assert abs(x[-1] - width) < max_cell
    # Cells never grow from offshore (left) to landward (right).
    assert np.all(np.diff(dx) <= 1e-9)


def test_threshold_layout():
    width, height, dy, min_size, max_size, crossing = 1000.0, 600.0, 15.0, 2.0, 20.0, 600.0
    x, y = create_threshold_based_adaptive_grid(
        width, height, dy, min_size, max_size, crossing, 1.05
    )
    assert_valid_axis(x, width, max_size)
    dx = np.diff(x)
    assert dx.max() == pytest.approx(max_size)
    # Equalising the boundary cells shifts the layout by less than one coarse
    # cell, so the fine zone starts within max_size of the crossing.
    np.testing.assert_allclose(dx[x[:-1] >= crossing + max_size], min_size)
    assert np.any(dx[x[:-1] < crossing] > min_size)
    assert len(y) == int(np.ceil(height / dy)) + 1


def test_threshold_layout_clips_crossing_to_domain():
    x, _ = create_threshold_based_adaptive_grid(100.0, 50.0, 10.0, 1.0, 5.0, 250.0, 1.1)
    assert_valid_axis(x, 100.0, 5.0)


def test_left_to_right_layout():
    width, height, dy, min_size, max_size = 800.0, 400.0, 20.0, 2.0, 15.0
    x, y = create_left_to_right_adaptive_grid(width, height, dy, min_size, max_size)
    assert_valid_axis(x, width, max_size)
    dx = np.diff(x)
    assert dx[0] == dx[1] and dx[-1] == dx[-2]  # boundary cells match neighbours
    assert dx[0] <= max_size
    assert dx[-1] == pytest.approx(min_size, abs=0.1 * min_size)
    assert len(y) == int(np.ceil(height / dy)) + 1
