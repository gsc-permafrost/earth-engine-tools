# -*- coding: utf-8 -*-
"""
aggregate_aufeis
*DESCRIPTION*

Author: rparker
Created: 2026-04-15
"""

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon


def aggregate_aufeis(data: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    data["ice_id"] = data.index
    buffered = data.copy(deep=True)
    buffered["geometry"] = buffered.geometry.buffer(22.5)
    clusters = buffered.dissolve()
    clusters = clusters.explode(index_parts=False).reset_index(drop=True)
    clusters["cluster_id"] = clusters.index
    data_with_cluster_info = gpd.sjoin(data, clusters[["geometry", "cluster_id"]], how="left", predicate="intersects")
    year_columns = [c for c in data_with_cluster_info.columns if c.startswith("y_")]
    aggregation = {"area_m": "sum"}
    for year_col in year_columns:
        aggregation[year_col] = "max"
    aggregated_data = data_with_cluster_info.dissolve(by="cluster_id", aggfunc=aggregation)
    aggregated_data["geometry"] = [MultiPolygon([feature]) if isinstance(feature, Polygon)
                                   else feature for feature in aggregated_data["geometry"]]
    for year_col in year_columns:
        aggregated_data.loc[aggregated_data[year_col] != 0, year_col] = 1
    aggregated_data["frequency"] = aggregated_data[year_columns].sum(axis=1)
    return data_with_cluster_info, aggregated_data
