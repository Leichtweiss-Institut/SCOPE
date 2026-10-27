"""
Grid geometry without QGIS: rotation and node coordinate construction.
"""
import math

import numpy as np


def rot_point(x, y, ang_deg, ox, oy):
    """
    Rotate a point around an origin.

    Args:
        x, y: Point coordinates
        ang_deg: Rotation angle in degrees
        ox, oy: Origin coordinates

    Returns:
        tuple: (x, y) rotated coordinates
    """
    r = math.radians(ang_deg)
    c, s = math.cos(r), math.sin(r)
    return (x - ox) * c - (y - oy) * s + ox, (x - ox) * s + (y - oy) * c + oy


def to_local_frame(x, y, ang_deg, ox, oy, ll_x, ll_y):
    """
    Map world points into the unrotated model frame with the lower-left corner at (0, 0).

    Inverse of the rotation used to place the grid nodes.

    Args:
        x, y: Arrays of world coordinates
        ang_deg: Grid rotation angle in degrees
        ox, oy: Rotation centre
        ll_x, ll_y: Unrotated lower-left corner

    Returns:
        tuple: (local_x, local_y) arrays
    """
    theta = np.radians(-ang_deg)
    c, s = np.cos(theta), np.sin(theta)
    dxg = x - ox
    dyg = y - oy
    unrot_x = ox + c * dxg - s * dyg
    unrot_y = oy + s * dxg + c * dyg
    return unrot_x - ll_x, unrot_y - ll_y


def uniform_axes(width, height, dx, dy):
    """
    Node positions along x and y for a uniform grid in local coordinates.

    The last node may lie beyond ``width`` or ``height`` so the domain is fully covered.

    Returns:
        tuple: (x_coords, y_coords)
    """
    nx = int(np.ceil(width / dx)) + 1
    ny = int(np.ceil(height / dy)) + 1
    return np.arange(nx) * dx, np.arange(ny) * dy


def node_rows(x_axis, y_rows, ll_x, ll_y, ang_deg, ox, oy):
    """
    World coordinates of the grid nodes in the given rows.

    Uses the same operations in the same order as ``rot_point``, so the
    result is bit-identical to rotating each node on its own.

    Args:
        x_axis: Local node positions along x
        y_rows: Local y positions of the rows to compute
        ll_x, ll_y: Unrotated lower-left corner
        ang_deg: Rotation angle in degrees
        ox, oy: Rotation centre

    Returns:
        tuple: (XG, YG) arrays of shape (len(y_rows), len(x_axis))
    """
    r = math.radians(ang_deg)
    c, s = math.cos(r), math.sin(r)
    dx = (ll_x + np.asarray(x_axis, dtype=float)) - ox
    dy = (ll_y + np.asarray(y_rows, dtype=float)) - oy
    dx, dy = dx[np.newaxis, :], dy[:, np.newaxis]
    return dx * c - dy * s + ox, dx * s + dy * c + oy


def node_coordinates(x_axis, y_axis, ll_x, ll_y, ang_deg, ox, oy):
    """
    World coordinates of all grid nodes.

    Args:
        x_axis, y_axis: Local node positions along x and y
        ll_x, ll_y: Unrotated lower-left corner
        ang_deg: Rotation angle in degrees
        ox, oy: Rotation centre

    Returns:
        tuple: (XG, YG) arrays of shape (ny, nx)
    """
    return node_rows(x_axis, y_axis, ll_x, ll_y, ang_deg, ox, oy)
