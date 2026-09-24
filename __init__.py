"""
SCOPE - Spatial Coastal Operations and Processing Engine.

Copyright (C) 2026 Felix Ritter

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 2 of the License, or (at your option) any later
version. See the LICENSE file for details.

SPDX-License-Identifier: GPL-2.0-or-later
"""

__version__ = "1.0.0"


def classFactory(iface):  # pragma: no cover - exercised only inside QGIS
    """Entry point QGIS calls to instantiate the plugin.

    Args:
        iface: A QgisInterface instance provided by QGIS.

    Returns:
        The plugin instance managing the GUI integration.
    """
    from .plugin import ScopePlugin
    return ScopePlugin(iface)
