# -*- coding: utf-8 -*-
"""
vectorize_data
*DESCRIPTION*

Author: rparker
Created: 2026-04-14
"""

from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio as rio
from rasterio.features import shapes as rio_shapes
from shapely.geometry import shape as shapely_shape
import pyogrio

scratch = Path(r"c:\scratch\vectorize_gee")


def vectorize_gee_export(download_dir: str | Path, output_dir: str | Path, no_data: int = 99):
    if isinstance(download_dir, str):
        download_dir = Path(download_dir)
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    pyogrio.set_gdal_config_options({"OGR_GEOJSON_MAX_OBJ_SIZE": "0"})
    scratch.mkdir(exist_ok=True)

    tif_list = download_dir.glob("*.tif")
    working_crs = None
    data_to_compile = dict()
    for tif_file in tif_list:
        file_name = tif_file.stem
        with rio.open(tif_file) as image:
            if working_crs is None:
                working_crs = image.crs
            else:
                if image.crs != working_crs:
                    raise ValueError("CRS not same!")
            for ix, band_name in zip(image.indexes, image.descriptions):
                geojson_path = Path(scratch, f"{file_name}_{band_name}.geojson")
                if geojson_path.exists():
                    if band_name in data_to_compile:
                        data_to_compile[band_name].append(geojson_path)
                    else:
                        data_to_compile[band_name] = [geojson_path]
                    continue
                band = image.read(ix)
                unique_vals = np.unique(band)
                if unique_vals.size == 1 and unique_vals[0] == no_data:
                    continue
                if no_data is not None:
                    mask = band != no_data
                else:
                    mask = None
                pixel_shapes = rio_shapes(band, mask=mask, transform=image.transform)
                geometries, pixel_values = zip(*((shapely_shape(g), v) for g, v in pixel_shapes))
                vectorized_data = gpd.GeoDataFrame(list(pixel_values), columns=["pixel_value"],
                                                   geometry=list(geometries), crs=working_crs)
                vectorized_data.to_file(geojson_path, driver="GeoJSON")
                if band_name in data_to_compile:
                    data_to_compile[band_name].append(geojson_path)
                else:
                    data_to_compile[band_name] = [geojson_path]

    for dataset_name, file_list in data_to_compile.items():
        dataset = None
        output_path = Path(output_dir, f"{dataset_name}.geojson")
        for file_path in file_list:
            if dataset is None:
                dataset = gpd.read_file(file_path)
            else:
                new_data = gpd.read_file(file_path)
                dataset = pd.concat([dataset, new_data], ignore_index=True)
        dataset.to_file(output_path, driver="GeoJSON")
        dataset.to_file(Path(output_dir, "vectorized_data.gdb"), layer=dataset_name, driver="OpenFileGDB",
                        engine="pyogrio", layer_options={"TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER"})
    shutil.rmtree(scratch, ignore_errors=True)
    return
