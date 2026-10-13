# Sample data

A small dataset for trying SCOPE in QGIS without downloading bathymetry or
drawing polygons first. It covers a sandy beach with a foredune ridge and a
salt marsh on the Eiderstedt peninsula (German North Sea coast,
Schleswig-Holstein), the site used in the SCOPE article.

| File | Content | CRS |
| --- | --- | --- |
| `2022_sampleData.tiff` | Elevation in m above mean sea level, 10 m resolution, 4.3 × 3.1 km | EPSG:25832 |
| `veg_0.3.gpkg` | Sparse dune vegetation | EPSG:4326 |
| `veg_0.5.gpkg` | Medium dune vegetation | EPSG:4326 |
| `veg_0.7.gpkg` | Dense dune vegetation | EPSG:4326 |
| `veg_1.0.gpkg` | Salt marsh (landward) | EPSG:4326 |

Each polygon file is named after the vegetation density assigned to it in the
example below. The polygons are in EPSG:4326 on purpose: SCOPE reprojects them
to the working CRS.

## Try it

1. Drag `2022_sampleData.tiff` and the four `veg_*.gpkg` files into an empty
   QGIS project. Set the project CRS to EPSG:25832.
2. Start SCOPE, click **Select bathymetry data** and select `2022_sampleData`.
3. Under **Model area parameters**, choose the anchor, width, height and rotation. Click **Create model area** and click
   on the map canvas. Any domain inside the raster works.
4. Under **Grid parameters**, set Δx and Δy. For adaptive refinement, set
   Min Δx, Max Δx and a bed level threshold (e.g. the dune toe).
5. Under **Custom grid files**, add a grid with the preset **Vegetation density
   (veg.grd)** and give the four layers the values in their file names
   (0.3, 0.5, 0.7, 1.0).
6. Optionally click **Threshold mask**, select `veg_1.0` and give it a real
   and imaginary part; nodes outside it keep the default `1.0+0.0j`.
7. Click **Process selected area** and choose an output folder.

SCOPE writes `x.grd`, `y.grd`, `z.grd`, `veg.grd` (and `threshold_mask.grd`)
together with a run log of all settings.

## Sources and licences

**Elevation:** clipped from the TrilaWatt annual topography 2022 for the German
Bight. © Bundesanstalt für Wasserbau (BAW), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The data were clipped
to the area above and not otherwise changed. Intended for teaching and
research, not suitable for navigation.

> Milbradt, P., Pineda Leiva, D. F. (2025): TrilaWatt: Topographie (1996-2014,
> 2022) [Data set]. Bundesanstalt für Wasserbau.
> <https://doi.org/10.48437/4baaf0-aeaf58>

**Vegetation polygons:** digitised by the SCOPE authors and released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). They are
illustrative and not a validated vegetation survey.

The GPL licence of the SCOPE code does not apply to the files in this folder.
