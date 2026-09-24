# SCOPE

**Spatial Coastal Operations and Processing Engine**: a QGIS plugin that
generates model-ready grid files for the coastal models XBeach and AeoLiS from
raster bathymetry and vector polygon layers.

You draw and rotate a model domain on the QGIS map, and SCOPE writes:

- `x.grd`, `y.grd`, `z.grd`: node coordinates and interpolated bed elevation
- custom grid files: user-named value grids from polygon layers, for example
  vegetation (`veg.grd`), XBeach hard layers (`ne_layer.grd`) or bed friction
  (`bedfriction.grd`)
- `threshold_mask.grd`: a complex-valued mask for AeoLiS

## Features

- Interactive model domain: centre or XBeach-origin anchor, width, height,
  rotation, and dragging to reposition
- Uniform grids, or adaptive cross-shore refinement driven by a bed level
  threshold (fine landward, coarse offshore)
- Output in local model coordinates or in world coordinates of a selectable
  working CRS (the project CRS by default)
- Any number of custom grid files, with presets for vegetation density,
  vegetation type, hard layer and bed friction
- Splitting the domain into sub-areas, and batch processing of several rasters
- Optional preview panes for grid spacing, bed level (2D and 3D) and custom grids
- A timestamped run log next to the outputs, recording all settings

## Requirements

- QGIS 3.40 or later (tested with 3.40 to 3.44)
- NumPy, SciPy, Matplotlib and GDAL. These ship with the QGIS installers for
  Windows and macOS. On Linux, install them with your package manager if they
  are missing. Without SciPy, SCOPE falls back to nearest-neighbour
  interpolation. Matplotlib is only needed for the preview panes.

## Installation

**From a ZIP file.** Build `SCOPE.zip` from the QGIS Python console
(*Plugins → Python Console*), using the full path to `build_plugin.py`:

```python
# Linux / macOS
import runpy; runpy.run_path('/path/to/SCOPE/build_plugin.py', run_name='__main__')

# Windows
import runpy; runpy.run_path(r'C:\path\to\SCOPE\build_plugin.py', run_name='__main__')
```

Alternatively, run `python build_plugin.py` in a terminal (on Windows, the
*OSGeo4W Shell* installed with QGIS). The ZIP is created next to
`build_plugin.py`. Then in QGIS choose *Plugins → Manage and Install Plugins →
Install from ZIP* and select `SCOPE.zip`.

**From source.** Copy or link the repository folder into your QGIS plugin
folder and enable SCOPE in *Plugins → Manage and Install Plugins*. The folder
name does not matter, so a GitHub download named `SCOPE-main` works as is:

- Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
- Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`

SCOPE then appears in the toolbar and under *Plugins → SCOPE*.

**For development.** Open `launcher.py` in the QGIS Python console's editor and
run it, or run it from the console:

```python
path = '/path/to/SCOPE/launcher.py'
exec(open(path).read(), {'__file__': path})
```

The launcher imports the repository under its folder name and reloads all SCOPE
modules on every run, so code changes take effect without restarting QGIS. On
Windows, use forward slashes or a raw string for the path, for example
`r'C:\Users\me\SCOPE-main\launcher.py'`.

## Quick start

1. Load a bathymetry raster (and any polygon layers) into a QGIS project.
2. Start SCOPE and click **Select bathymetry data**. Selecting several rasters
   enables batch processing.
3. Under **Model area parameters**, set anchor point, width, height and
   rotation, then click **Create model area** and click on the map. Use
   **Move model area** to reposition it.
4. Under **Grid parameters**, set Δx and Δy. For adaptive refinement, open
   **Use adaptive grid resolution (cross-shore)** and set Min Δx, Max Δx, the
   bed level threshold and the longshore Δy.
5. Under **Processing options**, choose local or world coordinates and the
   working CRS.
6. Optionally add **Custom grid files**, define a **Threshold mask**, or
   **Split model area**, and select the preview panes to open.
7. Click **Process selected area** and choose where to save the output.

## Outputs

| File | Content |
| --- | --- |
| `x.grd`, `y.grd` | Node coordinates |
| `z.grd` | Bed elevation, linearly interpolated from the raster (nearest value outside the data hull) |
| custom grids | One value per polygon layer at each node, default value elsewhere |
| `threshold_mask.grd` | Complex values in AeoLiS format `(real+imagj)` |
| `*_clipped.xyz` | Raster samples used for interpolation |
| `processing.log` | Run settings and statistics (`batch_processing.log` and `split_processing.log` for batch and split runs) |

All grids have the same node shape as `x.grd`. Batch runs write one subfolder
per raster. Split runs write one subfolder per sub-area, named
`{raster}_area_row{r}_col{c}`, and prefix the file names with it.

## Project structure

```text
SCOPE/
├── __init__.py, plugin.py   QGIS plugin entry point and toolbar/menu integration
├── main.py, launcher.py     Python console entry point and development launcher
├── metadata.txt, icon.png   Plugin metadata and icon read by QGIS
├── build_plugin.py          Builds the installable SCOPE.zip
├── gui/                     Dialogs (main window, welcome screen, layer selection,
│                            custom grid definition, threshold mask)
├── core/map_tools.py        Drawing and moving the model domain on the map
├── processing/
│   ├── raster.py            Raster clipping, reprojection and XYZ export
│   ├── custom_grid.py       Custom grid files from polygon layers
│   └── grid/
│       ├── pipeline.py      Node layout, interpolation and output files
│       ├── threshold.py     Adaptive cross-shore layouts and threshold mask
│       └── preview.py       Matplotlib preview panes
├── utils/                   Working CRS, geometry helpers, layer tree grouping
├── docs/                    Additional documentation
└── LICENSE                  GNU GPL v2
```

The processing package has no dependency on the dialogs and can be called from
scripts in a QGIS Python environment.

See [docs/CUSTOM_GRID_ALGORITHM.md](docs/CUSTOM_GRID_ALGORITHM.md) for how
custom grid files are computed.

## Troubleshooting

- **No layers in the selection dialogs:** load the raster and polygon layers
  into the current QGIS project first.
- **Model area in the wrong place:** SCOPE digitises the domain in the project
  CRS. Set the project CRS to the CRS you want to work in.
- **Slow custom grids:** run time grows with the number of nodes and polygons.
  Use a coarser grid or simplify the polygons.

## Support

Questions and bug reports: felix.ritter@tu-braunschweig.de

## Citation

If you use SCOPE in your research, please cite the accompanying article
(reference to follow).

## License

SCOPE is released under the GNU General Public License, version 2 or (at your
option) any later version. See [LICENSE](LICENSE).
