# -*- coding: utf-8 -*-
"""
static_masks
*DESCRIPTION*

Author: rparker
Created: 2026-04-13
"""

import ee

from .gee_project import GEEProject


class StaticMasks(GEEProject):

    def __init__(self, project_name, tpi=[2, 10], elevation=1100, slope=20, aspect=None, hand=15,
                 initialize=True):  # Aspect could be a 3 element list [slope, bearing1, bearing2], default [10,54,315]?
        super().__init__(project_name)

        # dicts for data and masks
        # self.masks = {}
        # set class values to pass to mapped functions
        self.tpi_threshold = tpi
        self.elevation_threshold = elevation
        self.slope_threshold = slope
        self.aspect_threshold = aspect
        self.hand_threshold = hand
        self.terrain_masks = {}
        self.combined_terrain_mask = None
        self.gsw_water_mask = None
        if initialize:
            self.create_terrain_mask()
            self.create_gsw_water_mask()
        return

    def create_terrain_mask(self):
        # Execute terrain classifications
        dem_collection = ee.ImageCollection(
            [ee.Image("UMN/PGC/ArcticDEM/V4/2m_mosaic")
             .reproject(crs=ee.Image("UMN/PGC/ArcticDEM/V4/2m_mosaic").projection(), scale=30)])
        # Elevation & HAND are simple exceedance threshold masks
        self.terrain_masks['elevation'] = dem_collection.map(self.elevation_mask).mosaic()
        # TPI is the exceedance threshold and the calculation radius
        self.terrain_masks['tpi'] = dem_collection.map(self.tpi_mask).mosaic()
        # Slope gives 3 classes (-1 "flat" [slope<1], 1 not flat, 0 exceeded slope threshold)
        # flat can be combined with GSW to discriminate between lakes/large rivers which need a buffer and small sloped streams/wetlands which may not need to be masked at all? or at least don't need a buffer
        self.terrain_masks['slope'] = dem_collection.map(self.slope_mask).mosaic()

        self.terrain_masks['hand'] = self.create_hand_mask()
        self.combined_terrain_mask = ee.Image.constant(1).rename('Mask')
        for key, value in self.terrain_masks.items():
            self.combined_terrain_mask = self.combined_terrain_mask.multiply(value)
        return

    def create_gsw_water_mask(self):
        global_surface_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
        self.gsw_water_mask = global_surface_water.select("occurrence").gt(50).unmask(0)

    # Functions for topographic Masking
    def tpi_mask(self, image):
        window_radius = self.tpi_threshold[1]
        elevation = image.select("elevation")
        tpi = elevation.subtract(elevation.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.square(window_radius))) \
            .rename(f"TPI_{window_radius}")
        image = image.addBands(tpi)
        exp = f"TPI < {self.tpi_threshold[0]}"
        dic = {"TPI": image.select("TPI_..?")}
        tpi_classified = image.expression(exp, dic).rename("Mask")
        return tpi_classified

    def slope_mask(self, image):
        elevation = image.select("elevation")
        slope = ee.Terrain.slope(elevation).rename("Slope")
        image = image.addBands(slope)
        exp = f"Slope < {self.slope_threshold}"
        dic = {"Slope": image.select("Slope")}
        slope_classified = image.expression(exp, dic).rename("Mask")
        return slope_classified

    def aspect_mask(self, image):
        elevation = image.select("elevation")
        aspect = ee.Terrain.aspect(elevation).rename("Aspect")
        image = image.addBands(aspect)
        exp = (f"!(Slope > {self.aspect_threshold[0]} && (Aspect < {self.aspect_threshold[1]} "
               f"|| Aspect > {self.aspect_threshold[2]}))")
        dic = {"Slope": image.select("Slope"), "Aspect": image.select("Aspect")}
        aspect_classified = image.expression(exp, dic).rename("Mask")
        return aspect_classified

    def elevation_mask(self, image):
        exp = f"elevation < {self.elevation_threshold}"
        dic = {"elevation": image.select("elevation")}
        elev_classified = image.expression(exp, dic).rename("Mask")
        return elev_classified

    def create_hand_mask(self):
        # Height Above Nearest Drainage Mask
        hand90_1000 = ee.Image("users/gena/GlobalHAND/90m-global/hand-1000")
        exp = f"hand < {self.hand_threshold}"
        dic = {"hand": hand90_1000.select("b1")}
        hand_classified = hand90_1000.expression(exp, dic).rename("Mask")
        return hand_classified
