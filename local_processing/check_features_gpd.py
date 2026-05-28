# -*- coding: utf-8 -*-
"""
check_features_gpd
*DESCRIPTION*

Author: rparker
Created: 2026-03-03
"""

import geopandas as gpd
import pandas as pd


def small_infrequent_pixel_filtering(data: gpd.GeoDataFrame, area_field: str = "area_m",
                                     frequency_field: str = "frequency") -> gpd.GeoDataFrame:
    # establish consistent index for merging and ensure area is correct
    data["ice_id"] = data.index
    data[area_field] = data.area
    # establish working datasets
    filtering_data = data.copy()
    # subset low frequency (2 or less) features 4 pixels or less, and all features less than 1.5 pixels
    buffered = data.loc[((data[frequency_field] <= 2) & (data[area_field] <= 3600)) | (data[area_field] <= 1350)].copy()
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
                                                     filter=("filter", "max")).reset_index()
    cluster_stats = cluster_stats.loc[cluster_stats["filter"]]
    # identify clusters to be removed (6 pixels or less)
    small_clusters = cluster_stats.loc[cluster_stats["total_area"] <= 5400]["cluster_id"]
    remove_list = joined.loc[joined["cluster_id"].isin(small_clusters)]["ice_id"].tolist()
    # remove features from dataset
    good_data = data.loc[~data["ice_id"].isin(remove_list)]
    return good_data.drop(columns=["ice_id", "filter"])
