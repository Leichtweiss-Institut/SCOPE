# Custom Grid Files

SCOPE builds user-defined **custom grid files** from polygon layers, for example
a vegetation map (`veg.grd`), an XBeach hard layer (`ne_layer.grd`) or a bed
friction map (`bedfriction.grd`). Each grid assigns one value per polygon layer
to every grid node inside that layer's polygons, over a default background
value. The implementation is in
[`processing/custom_grid.py`](../processing/custom_grid.py).

## Inputs

Each grid is described by a `CustomGridDefinition`:

```python
CustomGridDefinition(
    filename="veg.grd",          # output file name ('.grd' appended if missing)
    layer_values={               # {QgsVectorLayer: value}
        saltwater_meadow_layer: 0.8,
        dune_vegetation_layer:  0.6,
    },
    default_value=0.0,           # value for nodes outside all polygons
    decimals=3,                  # output decimal places; 0 writes integers
    enabled=True,                # generated during processing
    show_preview=True,           # open a preview pane after processing
)
```

In the GUI, definitions are managed in the "Custom grid files" section (add,
edit, duplicate, remove). Presets are provided for vegetation density,
vegetation type, hard layer and bed friction. Integer grids such as a
vegetation type map are definitions with `decimals=0`.

## Algorithm

### 1. Node grid

The grid has the node coordinates `XA`, `YA` of shape `(ny, nx)`, the same
shape as `x.grd`, `y.grd` and `z.grd`. Values are evaluated at the nodes
themselves, because XBeach (`ne_layer`, `bedfricfile`, `veggiemapfile`) and
AeoLiS (`veg_file`) expect parameter grids of that shape. Each grid starts
filled with its default value.

### 2. Layer preprocessing

For each layer (`_process_layers`), every feature geometry is

1. reprojected to the working CRS, with one `QgsCoordinateTransform` per layer;
2. translated by `(-origin_x, -origin_y)` when local coordinates are selected;
3. dropped if it is invalid (`isGeosValid()`) or empty;
4. dropped if its bounding box does not intersect the grid extent.

Layers removed from the QGIS project after being selected are skipped.

### 3. Containment test per node

The retained geometries of a layer go into a `QgsSpatialIndex` (R-tree), and
their bounding boxes are cached. For every node (`_process_layer`):

```python
for geom_id in spatial_index.nearestNeighbor(node_point, 10):
    bounds = geom_bounds[geom_id]
    if bounds.xMinimum() <= x <= bounds.xMaximum() and \
       bounds.yMinimum() <= y <= bounds.yMaximum():
        candidate_ids.append(geom_id)

for geom_id in candidate_ids:
    if geom_dict[geom_id].contains(node_point):
        grid[i, j] = value
        break
```

The exact test is `QgsGeometry.contains`, so polygon boundaries are used
without simplification. Nodes are processed in batches of 50,000 only to keep
QGIS responsive and to report progress.

### 4. Layer order

Layers are processed in order and write directly into the grid, so later
layers override earlier ones where they overlap. The order follows the layer
order in the QGIS project.

## Output

Each grid is written as space-separated rows with the definition's number of
decimals (`_write_grid`). For split areas, the area prefix
(`{raster}_{area}_`) is added to the filename as for `x.grd`, `y.grd` and
`z.grd`. If previews are enabled, both globally and for the definition, each
grid opens in its own matplotlib pane.

Per-layer statistics (nodes updated, coverage, time) are written to the run
log.

## Performance

Work per node is roughly constant, so run time scales linearly with the node
count `N = ny * nx` for each definition, at about 10^5 nodes per second on one
core. It also depends on the number and complexity of the polygons.

## Notes

- `nearestNeighbor(node_point, 10)` returns the ten nearest features. A
  polygon that contains the node has distance zero and is always among them,
  unless more than ten polygons overlap at that node.
- The same code path is used for every grid size and every definition.
- The AeoLiS threshold mask (`threshold_mask.grd`) uses this routine as well,
  with complex values written as `(real+imagj)` at full precision.
