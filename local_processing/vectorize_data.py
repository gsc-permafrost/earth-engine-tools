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
import warnings


def vectorize_gee_export(download_dir: str | Path, output_dir: str | Path, no_data: int = None):
    if isinstance(download_dir, str):
        download_dir = Path(download_dir)
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    pyogrio.set_gdal_config_options({"OGR_GEOJSON_MAX_OBJ_SIZE": "0"})

    scratch_dir = Path(r"c:\scratch\vectorize_gee")
    scratch_dir.mkdir(exist_ok=True, parents=True)
    # work within try block to utilize finally functionality to clean up regardless of success
    try:
        # initialize variables
        tif_list = download_dir.glob("*.tif")
        working_crs = None
        data_to_compile = dict()
        # iterate through images
        for tif_file in tif_list:
            file_name = tif_file.stem
            # open image
            with rio.open(tif_file) as image:
                if working_crs is None:
                    working_crs = image.crs
                else:
                    if image.crs != working_crs:
                        raise ValueError("CRS not same!")
                # iterate through image bands
                for ix, band_name in zip(image.indexes, image.descriptions):
                    # load band to numpy array
                    band = image.read(ix)
                    if no_data is None:
                        no_data = image.nodatavals[ix - 1]
                    unique_vals = np.unique(band)
                    # if band has no data skip it
                    if unique_vals.size == 1 and unique_vals[0] == no_data:
                        continue
                    # convert raster to GeoDataFrame
                    if no_data is not None:
                        mask = band != no_data
                    else:
                        mask = None
                    pixel_shapes = rio_shapes(band, mask=mask, transform=image.transform)
                    geometries, pixel_values = zip(*((shapely_shape(g), v) for g, v in pixel_shapes))
                    vectorized_data = gpd.GeoDataFrame(list(pixel_values), columns=["pixel_value"],
                                                       geometry=list(geometries), crs=working_crs)
                    # save GeoDataFrame in scratch directory temporarily and add temporary path to dictionary
                    geojson_path = Path(scratch_dir, f"{file_name}_{band_name}.geojson")
                    vectorized_data.to_file(geojson_path, driver="GeoJSON")
                    if band_name in data_to_compile:
                        data_to_compile[band_name].append(geojson_path)
                    else:
                        data_to_compile[band_name] = [geojson_path]
        # iterate through dictionary of temporary files
        for dataset_name, file_list in data_to_compile.items():
            dataset = None
            output_path = Path(output_dir, f"{dataset_name}.geojson")
            # compile all temporary files into one GeoDataFrame (for each dict key)
            for file_path in file_list:
                if dataset is None:
                    dataset = gpd.read_file(file_path)
                else:
                    new_data = gpd.read_file(file_path)
                    dataset = pd.concat([dataset, new_data], ignore_index=True)
            # save the compiled dataset to the specified directory
            dataset.to_file(output_path, driver="GeoJSON")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                dataset.to_file(Path(output_dir, "vectorized_data.gdb"), layer=dataset_name, driver="OpenFileGDB",
                                engine="pyogrio", layer_options={"TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER"})
    except Exception as e:
        raise e
    finally:
        # regardless of success remove scratch_dir
        shutil.rmtree(scratch_dir, ignore_errors=True)
    return
