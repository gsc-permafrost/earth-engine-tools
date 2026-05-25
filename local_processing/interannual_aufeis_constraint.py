# -*- coding: utf-8 -*-
"""
interannual_aufeis_constraint
*DESCRIPTION*

Author: rparker
Created: 2026-05-22
"""

from pathlib import Path
import numpy as np
import pandas as pd
import rasterio as rio
import regex as re


def interannual_aufeis_constraint(download_dir: str | Path, output_dir: str | Path):
    if isinstance(download_dir, str):
        download_dir = Path(download_dir)
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    tif_list = download_dir.glob("*.tif")

    image_db = pd.DataFrame()
    for tif_file in tif_list:
        ix = len(image_db.index)
        file_name = tif_file.stem
        if "interannual" in file_name:
            continue
        image_db.loc[ix, "path"] = tif_file
        image_db.loc[ix, "year"] = re.search(r"y\d{4}", file_name).group()[1:]
        image_db.loc[ix, "tile"] = re.search(r"tile_\d+", file_name).group().split("_")[-1]

    working_crs = None
    for tile in image_db["tile"].unique():
        total_aufeis = None
        total_flagged = None
        tile_transform = None
        subset = image_db.loc[image_db["tile"] == tile]
        for i, r in subset.iterrows():
            with rio.open(r["path"]) as image:
                if working_crs is None:
                    working_crs = image.crs
                else:
                    if image.crs != working_crs:
                        raise ValueError("CRS not same!")
                if tile_transform is None:
                    tile_transform = image.transform
                else:
                    if image.transform != tile_transform:
                        raise ValueError("transform not same!")
                band_names = list(image.descriptions)
                aufeis_band_ix = 1 + band_names.index(f"aufeis_{r['year']}")
                aufeis_band = image.read(aufeis_band_ix)
            flagged = (aufeis_band > 0).astype(np.int8)
            if total_aufeis is None:
                total_aufeis = aufeis_band
                total_flagged = flagged
            else:
                total_aufeis = total_aufeis + aufeis_band
                total_flagged = total_flagged + flagged
        aufeis_score = np.divide(total_aufeis, total_flagged, out=np.zeros_like(total_aufeis.astype(np.float64)),
                                 where=total_flagged != 0)
        insufficient_data = total_flagged < 4
        aufeis_score[insufficient_data] = 0
        interannual_aufeis = (aufeis_score > 2.5).astype(np.int8)
        output_meta = {"driver": "GTiff",
                       "width": interannual_aufeis.shape[1],
                       "height": interannual_aufeis.shape[0],
                       "count": 1,
                       "dtype": "uint8",
                       "crs": working_crs,
                       "transform": tile_transform}
        interannual_aufeis_path = Path(output_dir, f"interannual_aufeis_tile_{tile}.tif")
        with rio.open(interannual_aufeis_path, 'w', **output_meta) as dst:
            dst.write(interannual_aufeis, 1)
            dst.set_band_description(1, "interannual_aufeis")

        for i, r in subset.iterrows():
            with rio.open(r["path"]) as image:
                band_names = list(image.descriptions)
                aufeis_band_ix = 1 + band_names.index(f"aufeis_{r['year']}")
                aufeis_band = image.read(aufeis_band_ix)
                transform = image.transform
            if aufeis_band.shape != interannual_aufeis.shape:
                raise ValueError("shapes not same!")

            filtered_out = interannual_aufeis == 0
            aufeis_band[filtered_out] = 0
            output_meta = {"driver": "GTiff",
                           "width": aufeis_band.shape[1],
                           "height": aufeis_band.shape[0],
                           "count": 1,
                           "dtype": aufeis_band.dtype,
                           "crs": working_crs,
                           "transform": transform}
            constrained_aufeis_path = Path(output_dir, f"constrained_aufeis_y{r['year']}_tile_{tile}.tif")
            with rio.open(constrained_aufeis_path, 'w', **output_meta) as dst:
                dst.write(aufeis_band, 1)
                dst.set_band_description(1, f"constrained_aufeis_y{r['year']}")

    return


def main():
    interannual_aufeis_constraint(r"D:\icing_mapping\mosaic_testing\yaml_test\downloaded_data",
                                  r"D:\icing_mapping\mosaic_testing\yaml_test\interannual_constraint")
    return


if __name__ == '__main__':
    main()
