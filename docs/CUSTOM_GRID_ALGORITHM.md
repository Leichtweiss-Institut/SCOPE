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

The grid has `(ny, nx)` nodes, the same shape as `x.grd`, `y.grd` and
`z.grd`. Values are evaluated at the nodes themselves, because XBeach
(`ne_layer`, `bedfricfile`, `veggiemapfile`) and AeoLiS (`veg_file`) expect
parameter grids of that shape.

The node coordinates are never held for the whole grid. A `NodeGrid`
([`processing/grid/stream.py`](../processing/grid/stream.py)) yields them a
block of rows at a time (about 2 million nodes per block), and each block
starts filled with the default value. Memory use therefore does not depend on
the grid size.

### 2. Layer preprocessing

For each layer (`_process_layers`), every feature geometry is

1. reprojected to the working CRS, with one `QgsCoordinateTransform` per layer;
2. translated by `(-origin_x, -origin_y)` when local coordinates are selected;
3. dropped if it is invalid (`isGeosValid()`) or empty;
4. dropped if its bounding box does not intersect the grid extent. The
   extent is the exact min/max of the node coordinates, recorded while
   `x.grd` and `y.grd` are written.

Layers removed from the QGIS project after being selected are skipped.

### 3. Containment test per node

The retained geometries of a layer go into a `QgsSpatialIndex` (R-tree), and
their bounding boxes are cached (`_LayerIndex`). The index is built once per
layer and reused for every block. For every node of a block
(`_LayerIndex.assign`):

```python
for geom_id in spatial_index.nearestNeighbor(node_point, 10):
    bounds = geom_bounds[geom_id]
    if bounds.xMinimum() <= x <= bounds.xMaximum() and \
       bounds.yMinimum() <= y <= bounds.yMaximum():
        candidate_ids.append(geom_id)

for geom_id in candidate_ids:
    if geom_dict[geom_id].contains(node_point):
        block[i, j] = value
        break
```

The exact test is `QgsGeometry.contains`, so polygon boundaries are used
without simplification. Every 50,000 nodes, QGIS processes pending events to
stay responsive, and progress is logged as node checks (nodes × layers) with
an estimated remaining time.

### 4. Layer order

Within each block, layers are processed in order and write directly into the
block, so later layers override earlier ones where they overlap. The result is
the same as processing each layer over the whole grid. The order is the one in which
the layers are listed in the custom grid dialog. That list comes from
`QgsProject.mapLayers()`, which is sorted by layer ID, so in practice it follows
the layer names. It is not the order of the QGIS Layers panel.

## Output

Each block is written as space-separated rows with the definition's number of
decimals (`_format_row`) as soon as all layers have been applied to it. For split areas, the area prefix
(`{raster}_{area}_`) is added to the filename as for `x.grd`, `y.grd` and
`z.grd`. If previews are enabled, both globally and for the definition, each
grid opens in its own matplotlib pane. The preview uses values sampled while
writing: every node for grids up to 1000 nodes per axis, otherwise every k-th
row and column.

Per-layer statistics (nodes updated, coverage, time) are written to the run
log after the file is complete.

## Performance

Work per node is roughly constant, so run time scales linearly with the node
count `N = ny * nx` for each definition, at about 10^5 nodes per second on one
core. It also depends on the number and complexity of the polygons. Memory
use is set by the block size and the polygons, not by `N`. Before
processing, the main dialog estimates the run time and warns when it exceeds
about an hour (see the README).

## Notes

- `nearestNeighbor(node_point, 10)` returns the ten nearest features. A
  polygon that contains the node has distance zero and is always among them,
  unless more than ten polygons overlap at that node.
- The same code path is used for every grid size and every definition.
- The AeoLiS threshold mask (`threshold_mask.grd`) uses this routine as well,
  with complex values written as `(real+imagj)` at full precision.
