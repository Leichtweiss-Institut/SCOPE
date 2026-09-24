"""
Layer management utilities for SCOPE.

All SCOPE layers live under a single top-level legend group ("SCOPE layers").
Per-run processing artifacts go into a "Processed model area" subgroup that is
replaced on each run so only the latest processed area is shown.
"""

GROUP_NAME = "SCOPE layers"
PROCESSED_AREA_SUBGROUP = "Processed model area"


def get_or_create_layer_group():
    """Get or create the top-level 'SCOPE layers' legend group."""
    from qgis.core import QgsProject

    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup(GROUP_NAME)
    if group is None:
        group = root.insertGroup(0, GROUP_NAME)
    return group


def get_or_create_subgroup(subgroup_name):
    """Get or create a subgroup under the 'SCOPE layers' group."""
    parent = get_or_create_layer_group()
    sub = parent.findGroup(subgroup_name)
    if sub is None:
        sub = parent.insertGroup(0, subgroup_name)
    return sub


def add_layer_to_group(layer):
    """Add a layer to the top-level 'SCOPE layers' group."""
    from qgis.core import QgsProject

    group = get_or_create_layer_group()
    QgsProject.instance().addMapLayer(layer, False)  # False = don't add to legend root
    group.addLayer(layer)


def add_layer_to_subgroup(layer, subgroup_name, at_top=True):
    """Add a layer to a subgroup under 'SCOPE layers'."""
    from qgis.core import QgsProject

    sub = get_or_create_subgroup(subgroup_name)
    QgsProject.instance().addMapLayer(layer, False)
    if at_top:
        sub.insertLayer(0, layer)
    else:
        sub.addLayer(layer)


def clear_subgroup(subgroup_name):
    """Remove every layer from a subgroup so it can be refreshed."""
    from qgis.core import QgsProject

    root = QgsProject.instance().layerTreeRoot()
    parent = root.findGroup(GROUP_NAME)
    if parent is None:
        return
    sub = parent.findGroup(subgroup_name)
    if sub is None:
        return
    project = QgsProject.instance()
    # Removing the map layer also removes its tree node from the subgroup.
    for tree_layer in sub.findLayers():
        layer = tree_layer.layer()
        if layer is not None:
            project.removeMapLayer(layer.id())
