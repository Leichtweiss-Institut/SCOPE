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
    ny, nx = len(y_axis), len(x_axis)
    XG = np.zeros((ny, nx))
    YG = np.zeros((ny, nx))
    for ri in range(ny):
        y_loc = ll_y + y_axis[ri]
        for cj in range(nx):
            x_loc = ll_x + x_axis[cj]
            XG[ri, cj], YG[ri, cj] = rot_point(x_loc, y_loc, ang_deg, ox, oy)
    return XG, YG
