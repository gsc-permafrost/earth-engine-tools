# -*- coding: utf-8 -*-
"""
interactive_map
*DESCRIPTION*

Author: rparker
Created: 2026-04-13
"""

import ee
import geemap
from typing import Any


class Map(geemap.Map):

    def __init__(self, center, zoom, add_basemap, display_crs: str, display_scale: int):
        self.display_crs = display_crs
        self.display_scale = display_scale
        super().__init__(center=center, zoom=zoom, add_basemap=add_basemap)

    def addLayer(self,
                 ee_object: ee.FeatureCollection | ee.Feature | ee.Image | ee.ImageCollection,
                 vis_params: dict[str, Any] | None = None,
                 name: str | None = None,
                 shown: bool = True,
                 opacity: float = 1.0,
                 mask_zero: bool = False) -> None:
        if isinstance(ee_object, ee.Image):
            ee_object = ee_object.reproject(crs=self.display_crs, scale=self.display_scale)
            if mask_zero:
                ee_object = ee_object.updateMask(ee_object.eq(0).Not())
        super().addLayer(ee_object, vis_params, name, shown, opacity)
        return


class InteractiveMap:
    def __init__(self, aoi: list[list[float]]):
        self.zoomLevel = 10
        self.maskVis = {'min': 0, 'max': 1}
        self.colour_vis = {"palette": ["red", "yellow", "green", "blue"]}
        self.rgbVis = {'bands': ['red', 'green', 'blue'], 'min': 0, 'max': .5, 'gamma': 1.4}
        self.falseColorVis = {'bands': ['swir1', 'nir', 'red'], 'min': 0, 'max': .5, 'gamma': 1.4}
        self.blueVis = {'palette': ['black', 'white', 'blue'], 'min': 0, 'max': 1}

        self.aoi = ee.Geometry.Polygon(coords=aoi)
        self.map = None
        return

    def new_map(self, display_crs: str, display_scale: int):
        self.map = Map(center=self.aoi.centroid().coordinates().getInfo(), zoom=self.zoomLevel, add_basemap=False,
                       display_scale=display_scale, display_crs=display_crs)
        self.map.add_basemap("HYBRID")
        self.map.centerObject(self.aoi, self.zoomLevel)
        self.map.add_inspector()


