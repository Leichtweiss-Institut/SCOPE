"""
Tests for coordinate rotation and grid node construction.
"""
import math

import numpy as np
import pytest

from scope.processing.grid.gridmath import (
    node_coordinates,
    node_rows,
    rot_point,
    to_local_frame,
    uniform_axes,
)


@pytest.mark.parametrize(
    "ang, expected",
    [(0, (1.0, 0.0)), (90, (0.0, 1.0)), (180, (-1.0, 0.0)), (-90, (0.0, -1.0))],
)
def test_rot_point_about_origin(ang, expected):
    assert rot_point(1.0, 0.0, ang, 0.0, 0.0) == pytest.approx(expected, abs=1e-12)


def test_rot_point_about_offset_centre():
    # (3, 2) is (1, 0) from the centre (2, 2); a quarter turn gives (0, 1) from it.
    assert rot_point(3.0, 2.0, 90, 2.0, 2.0) == pytest.approx((2.0, 3.0), abs=1e-12)


def test_rot_point_keeps_centre_fixed():
    assert rot_point(5.0, -7.0, 37.0, 5.0, -7.0) == pytest.approx((5.0, -7.0))


def test_rot_point_preserves_distance_to_centre():
    ox, oy = 10.0, 20.0
    x, y = rot_point(13.0, 24.0, 123.4, ox, oy)
    assert math.hypot(x - ox, y - oy) == pytest.approx(5.0)


def test_to_local_frame_inverts_rotation():
    ang, ox, oy, ll_x, ll_y = 27.0, 500.0, 300.0, 100.0, 50.0
    local = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 25.0], [312.5, 87.25]])
    world = np.array([rot_point(ll_x + lx, ll_y + ly, ang, ox, oy) for lx, ly in local])
    lx, ly = to_local_frame(world[:, 0], world[:, 1], ang, ox, oy, ll_x, ll_y)
    np.testing.assert_allclose(lx, local[:, 0], atol=1e-9)
    np.testing.assert_allclose(ly, local[:, 1], atol=1e-9)


def test_uniform_axes_counts_and_spacing():
    x, y = uniform_axes(100.0, 45.0, 10.0, 10.0)
    assert len(x) == 11 and len(y) == 6
    np.testing.assert_allclose(np.diff(x), 10.0)
    assert x[0] == 0.0 and x[-1] == 100.0
    # 45 m is not a multiple of 10 m: the last node lies past the edge.
    assert y[-1] == 50.0


def test_node_coordinates_shape_and_origin():
    x, y = uniform_axes(80.0, 30.0, 10.0, 5.0)
    XG, YG = node_coordinates(x, y, 100.0, 200.0, 30.0, 140.0, 215.0)
    assert XG.shape == YG.shape == (len(y), len(x))
    assert (XG[0, 0], YG[0, 0]) == pytest.approx(rot_point(100.0, 200.0, 30.0, 140.0, 215.0))


def test_node_coordinates_keeps_spacing_under_rotation():
    x, y = uniform_axes(80.0, 30.0, 10.0, 5.0)
    XG, YG = node_coordinates(x, y, 0.0, 0.0, 33.0, 40.0, 15.0)
    np.testing.assert_allclose(np.hypot(np.diff(XG, axis=1), np.diff(YG, axis=1)), 10.0)
    np.testing.assert_allclose(np.hypot(np.diff(XG, axis=0), np.diff(YG, axis=0)), 5.0)


def test_node_coordinates_rows_follow_rotated_x_axis():
    x, y = uniform_axes(50.0, 20.0, 10.0, 10.0)
    XG, YG = node_coordinates(x, y, 0.0, 0.0, 90.0, 0.0, 0.0)
    # After a quarter turn, the local x axis points north.
    np.testing.assert_allclose(XG[0], 0.0, atol=1e-9)
    np.testing.assert_allclose(YG[0], x, atol=1e-9)


def test_node_coordinates_with_adaptive_axis():
    x = np.array([0.0, 20.0, 35.0, 45.0, 50.0])
    y = np.array([0.0, 10.0])
    XG, YG = node_coordinates(x, y, 5.0, 5.0, 0.0, 0.0, 0.0)
    np.testing.assert_allclose(XG[1], 5.0 + x)
    np.testing.assert_allclose(YG[:, 0], 5.0 + y)


def _node_coordinates_loop(x_axis, y_axis, ll_x, ll_y, ang_deg, ox, oy):
    """Node-by-node reference: the implementation before vectorisation."""
    XG = np.zeros((len(y_axis), len(x_axis)))
    YG = np.zeros((len(y_axis), len(x_axis)))
    for ri in range(len(y_axis)):
        y_loc = ll_y + y_axis[ri]
        for cj in range(len(x_axis)):
            x_loc = ll_x + x_axis[cj]
            XG[ri, cj], YG[ri, cj] = rot_point(x_loc, y_loc, ang_deg, ox, oy)
    return XG, YG


@pytest.mark.parametrize("ang", [0.0, 17.3, 90.0, -123.45, 271.0])
@pytest.mark.parametrize(
    "x_axis",
    [np.arange(41) * 0.7, np.array([0.0, 20.0, 35.0, 45.0, 50.0, 50.3])],
)
def test_node_coordinates_bit_identical_to_loop(ang, x_axis):
    # World-sized coordinates, where rounding differences would show up.
    y_axis = np.linspace(0.0, 37.0, 23)
    args = (x_axis, y_axis, 33310871.97, 6013534.45, ang, 33311000.5, 6013600.25)
    XG, YG = node_coordinates(*args)
    XR, YR = _node_coordinates_loop(*args)
    assert np.array_equal(XG, XR)
    assert np.array_equal(YG, YR)


def test_node_rows_matches_full_grid_slice():
    x, y = uniform_axes(80.0, 30.0, 10.0, 5.0)
    args = (100.0, 200.0, 30.0, 140.0, 215.0)
    XG, YG = node_coordinates(x, y, *args)
    XB, YB = node_rows(x, y[2:5], *args)
    assert np.array_equal(XB, XG[2:5])
    assert np.array_equal(YB, YG[2:5])
