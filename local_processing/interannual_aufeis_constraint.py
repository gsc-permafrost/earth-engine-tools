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
import geopandas as gpd
import regex as re


def small_or_low_value_filtering(data: gpd.GeoDataFrame, area_field: str = "area_m") -> gpd.GeoDataFrame:
    # establish consistent index for merging and ensure area is correct
    data["ice_id"] = data.index
    data[area_field] = data.area
    # establish working datasets
    filtering_data = data.copy()
    # subset features 3 pixels or less
    buffered = data.loc[(data[area_field] <= 900 * 3) | (data["pixel_value"] == 2)].copy()
    # flag subset features as to be considered when filtering is conducted
    data.loc[buffered["ice_id"], "filter"] = True
    data.loc[pd.isna(data["filter"]), "filter"] = False
    # buffer small features by 0.75 pixels
    buffered["geometry"] = buffered.geometry.buffer(22.5)
    # replace small infrequent pixel geometry with their buffered counterparts
    filtering_data.loc[buffered["ice_id"], "geometry"] = buffered["geometry"]
    # dissolve and explode to combine overlapping features and get cluster IDs
    clusters = filtering_data.dissolve()
    clusters = clusters.explode(index_parts=False).reset_index(drop=True)
    clusters["cluster_id"] = clusters.index
    # join cluster IDs to dataset
    joined = gpd.sjoin(data, clusters[["geometry", "cluster_id"]], how="left", predicate="intersects")
    # aggregate based on cluster ID and drop features not related to the above buffering
    cluster_stats = joined.groupby("cluster_id").agg(cluster_size=("ice_id", "count"),
                                                     total_area=(area_field, "sum"),
                                                     mean_value=("pixel_value", "mean"),
                                                     filter=("filter", "max")).reset_index()
    cluster_stats = cluster_stats.loc[cluster_stats["filter"]]
    # identify clusters to be removed (4 pixels or less)
    cluster_ids_to_remove = cluster_stats.loc[(cluster_stats["total_area"] <= 900 * 4)
                                              | (cluster_stats["mean_value"] < 3)]["cluster_id"]
    ice_ids_to_remove = joined.loc[joined["cluster_id"].isin(cluster_ids_to_remove)]["ice_id"]
    # remove features from dataset
    good_data = data.loc[~data["ice_id"].isin(ice_ids_to_remove)]
    return good_data.drop(columns=["ice_id", "filter"])


def interannual_aufeis_constraint(vectorized_dir: str | Path):
    # initialize
    if isinstance(vectorized_dir, str):
        vectorized_dir = Path(vectorized_dir)

    aufeis_layers = vectorized_dir.glob("aufeis_*.geojson")






    return


def main():
    test_dir = Path(r"D:\icing_mapping\mosaic_testing\large_test_area\testing")
    test_dir.mkdir(exist_ok=True, parents=True)
    data_path = Path(r"D:\icing_mapping\mosaic_testing\large_test_area\vectorized\aufeis_2004.geojson")
    data = gpd.read_file(data_path)
    data = data.loc[data["pixel_value"] != 0]
    x = small_or_low_value_filtering(data)
    x.to_file(Path(test_dir, f"filtered_{data_path.stem}.shp"))
    return


if __name__ == '__main__':
    main()
