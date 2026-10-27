# SCOPE

[![tests](https://github.com/Leichtweiss-Institut/SCOPE/actions/workflows/test.yml/badge.svg)](https://github.com/Leichtweiss-Institut/SCOPE/actions/workflows/test.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23495239.svg)](https://doi.org/10.5281/zenodo.23495239)

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

- QGIS 3.40 to 3.44 (QGIS 4 is not yet supported)
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

## Preparing input data

- **Elevation:** any raster format GDAL can read works. A GeoTIFF with one
  raster per survey is easiest. SCOPE reads band 1 as bed elevation in metres.
- **Several sources:** if the elevation comes from separate surveys, for example
  a ship-borne bathymetry and an airborne terrain model of the beach and dunes,
  merge them into one continuous raster first. In QGIS, use
  *Raster → Miscellaneous → Merge* or *Build Virtual Raster*. Where the inputs
  overlap, the raster listed last wins. All inputs must share the same CRS and
  vertical datum, so reproject with *Raster → Projections → Warp* if needed.
- **Polygon layers:** any vector layer with polygons works, in any CRS. SCOPE
  reprojects them to the working CRS. Where polygons of different layers
  overlap, the layer listed later in the custom grid dialog wins.

## Quick start

To try SCOPE without your own data, use the elevation raster and vegetation
polygons in [sample_data/](sample_data/README.md), which come with step-by-step
settings.

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

Each run appends a block to the log file, so repeated runs collect in one file.
The block starts with a header that records the time, the raster, the working
CRS, the domain (width, height, rotation and anchor), the coordinate output
mode, and either the uniform spacing or the adaptive settings (minimum and
maximum cell size, threshold and longshore spacing). It also lists the custom
grid files and threshold mask layers. The resulting node counts and, for every
custom grid and threshold mask, the number of nodes assigned per layer follow.
The log is enough to reproduce a set of grids without the QGIS session that
made them.

## Choosing grid settings

- **Cell size and raster resolution:** a cell size well below the sample
  spacing of the raster adds no information. SCOPE only interpolates between
  the same samples. Choose Δx and Min Δx with the survey resolution in mind.
- **Stay inside the raster:** nodes outside the area covered by raster data
  get the value of the nearest sample. This is fine for a narrow margin, but
  keep the model domain within the raster coverage.
- **Bed level threshold (adaptive grids):** the threshold decides where the
  fine zone starts, so it has the largest effect on the result. Look at a
  cross-shore profile of the site before setting it, for example at the dune
  toe. If the spacing preview shows the transition in the wrong place, adjust
  the threshold and run again. If no bed level in the domain exceeds the
  threshold, SCOPE falls back to a cell size that changes linearly across the
  domain and says so in the log.
- **Grid size:** grids are interpolated and written a block of rows at a
  time, so memory use does not grow with the number of nodes. It is set
  mainly by the number of raster samples in the model area (about 300 bytes
  each). Disk use and run time still grow with the node count: each node adds
  roughly 40 bytes to `x.grd`, `y.grd` and `z.grd`, plus each custom grid and
  the threshold mask. Before processing, SCOPE logs a size estimate. It asks
  for confirmation when a grid has more than 50 million nodes, when the
  output would fill more than 80 % of the free disk space, when the input
  samples need more than 70 % of the available memory, or when the custom
  grids would take more than about an hour.

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
│   ├── custom_grid.py       Custom grid files and threshold mask from polygon layers
│   └── grid/
│       ├── pipeline.py      Node layout, interpolation and output files
│       ├── stream.py        Block-wise node coordinates, interpolation and writing
│       ├── estimate.py      Size estimates for the large-run warning
│       ├── gridmath.py      Rotation and node coordinates
│       ├── threshold.py     Adaptive cross-shore layouts and threshold crossing
│       └── preview.py       Matplotlib preview panes
├── utils/                   Working CRS, geometry helpers, layer tree grouping
├── tests/                   Unit tests (run without QGIS)
├── sample_data/             Example raster and polygon layers for trying SCOPE
├── docs/                    Additional documentation
└── LICENSE                  GNU GPL v2
```

The processing package has no dependency on the dialogs and can be called from
scripts in a QGIS Python environment.

See [docs/CUSTOM_GRID_ALGORITHM.md](docs/CUSTOM_GRID_ALGORITHM.md) for how
custom grid files are computed.

## Running tests

The unit tests cover rotation, node coordinates, threshold crossing detection,
the adaptive layouts, block-wise processing (checked against processing the
whole grid at once) and the size estimates. They need NumPy, SciPy and pytest,
not QGIS:

```bash
pip install -r requirements-dev.txt
pytest
```

GitHub Actions runs the tests on Python 3.9 and 3.12 for every push and pull
request.

## Troubleshooting

- **No layers in the selection dialogs:** load the raster and polygon layers
  into the current QGIS project first.
- **Model area in the wrong place:** SCOPE digitises the domain in the project
  CRS. Set the project CRS to the CRS you want to work in.
- **Slow custom grids:** run time grows with the number of nodes and polygons.
  Use a coarser grid or simplify the polygons.
- **Size warning before processing:** the estimate in the dialog and the log
  shows which limit the run exceeds. Reduce the model area, use a coarser
  spacing or split the area. Splitting reduces memory use per sub-area, but
  not the total disk space.

## Support

Questions and bug reports: felix.ritter@tu-braunschweig.de

## Citation

If you use SCOPE in your research, please cite the accompanying article
(reference to follow) and the version of the software you used. Each release is
archived on Zenodo with its own DOI. For version 1.0.0:

> Ritter, F., Schweiger, C., Lojek, O., Goseberg, N. (2026). SCOPE: Spatial
> Coastal Operations and Processing Engine (v1.0.0) [Software]. Zenodo.
> <https://doi.org/10.5281/zenodo.23495240>

The DOI [10.5281/zenodo.23495239](https://doi.org/10.5281/zenodo.23495239)
always resolves to the latest version.

## License

SCOPE is released under the GNU General Public License, version 2 or (at your
option) any later version. See [LICENSE](LICENSE).
