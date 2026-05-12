# -*- coding: utf-8 -*-
"""
check_features_gpd
*DESCRIPTION*

Author: rparker
Created: 2026-03-03
"""

import geopandas as gpd


def remove_lone_pixels_geopandas(data: gpd.GeoDataFrame, area_field: str = "AREA_M") -> gpd.GeoDataFrame:
    data["ice_id"] = data.index
    small_polys = data.loc[data[area_field] <= 1350].copy()
    buffered = small_polys.copy()
    buffered["geometry"] = buffered.geometry.buffer(22.5)
    clusters = buffered.dissolve()
    clusters = clusters.explode(index_parts=False).reset_index(drop=True)
    clusters["cluster_id"] = clusters.index
    joined = gpd.sjoin(small_polys, clusters[["geometry", "cluster_id"]], how="left", predicate="intersects")
    cluster_stats = joined.groupby("cluster_id").agg(cluster_size=("ice_id", "count"),
                                                     total_area=("area_m", "sum")).reset_index()
    small_clusters = cluster_stats.loc[cluster_stats["cluster_size"] == 1]["cluster_id"]
    remove_list = joined.loc[joined["cluster_id"].isin(small_clusters)]["ice_id"].tolist()
    good_data = data.loc[~data["ice_id"].isin(remove_list)]
    return good_data.drop(columns="ice_id")


def frequency_masking_geopandas(data: gpd.GeoDataFrame, area_field: str = "AREA_M", frequency_field: str = "FREQUENCY"
                                ) -> gpd.GeoDataFrame:
    data["ice_id"] = data.index
    data[area_field] = data.area
    small_infrequent = data.loc[(data[frequency_field] <= 2) & (data[area_field] <= 3601)].copy()
    buffered = small_infrequent.copy()
    buffered["geometry"] = buffered.geometry.buffer(22.5)
    clusters = buffered.dissolve()
    clusters = clusters.explode(index_parts=False).reset_index(drop=True)
    clusters["cluster_id"] = clusters.index
    joined = gpd.sjoin(small_infrequent, clusters[["geometry", "cluster_id"]], how="left", predicate="intersects")
    cluster_stats = joined.groupby("cluster_id").agg(cluster_size=("ice_id", "count"),
                                                     total_area=(area_field, "sum")).reset_index()
    small_clusters = cluster_stats.loc[cluster_stats["total_area"] <= 5400]["cluster_id"]
    remove_list = joined.loc[joined["cluster_id"].isin(small_clusters)]["ice_id"].tolist()
    good_data = data.loc[~data["ice_id"].isin(remove_list)]
    return good_data.drop(columns="ice_id")
