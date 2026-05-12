# -*- coding: utf-8 -*-
"""
landsat_collection
*DESCRIPTION*

Author: rparker
Created: 2026-04-13
"""


import ee
import datetime as dt

from .static_masks import StaticMasks


class LandsatCollection(StaticMasks):
    def __init__(self, project_name, aoi, start_doy, end_doy, satellites, cloud_frac):

        def merge_collections(new, current):
            return ee.ImageCollection(current).merge(new)

        super().__init__(project_name)
        self.aoi = ee.Geometry.Polygon(coords=aoi)
        self.start_doy = start_doy
        self.end_doy = end_doy
        self.cloud_frac = cloud_frac
        self.optical_bands = None
        self.thermal_bands = None
        # self.brightness_masking_threshold = 0.9
        self.collection_paths = {9: "LANDSAT/LC09/C02/T1_L2",
                                 8: "LANDSAT/LC08/C02/T1_L2",
                                 7: "LANDSAT/LE07/C02/T1_L2",
                                 5: "LANDSAT/LT05/C02/T1_L2",
                                 4: "LANDSAT/LT04/C02/T1_L2"}

        self.collection = ee.ImageCollection(
            ee.List([self.get_collections(sat, self.collection_paths[sat]) for sat in satellites if sat in self.collection_paths])
            .iterate(merge_collections, ee.ImageCollection([])))
        return

    def get_collections(self, number, path):
        doy_today = dt.datetime.now().timetuple().tm_yday
        if doy_today > self.end_doy:
            end_year = dt.datetime.now().year
        else:
            end_year = dt.datetime.now().year - 1

        if number >= 8:
            self.optical_bands = [['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'],
                                  ['blue', 'green', 'red', 'nir', 'swir1', 'swir2']]
            self.thermal_bands = [['ST_B10'], ['lwir']]
        else:
            self.optical_bands = [['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'],
                                  ['blue', 'green', 'red', 'nir', 'swir1', 'swir2']]
            self.thermal_bands = [['ST_B6'], ['lwir']]
        collection = ee.ImageCollection(path).filter(ee.Filter.And(
            ee.Filter.calendarRange(1985, end_year, 'year'),
            ee.Filter.calendarRange(self.start_doy, self.end_doy, 'day_of_year'),
            ee.Filter.lt("CLOUD_COVER_LAND", self.cloud_frac),
            ee.Filter.bounds(self.aoi)
        )).map(self.reflectivity_and_spectral_indices)
        return collection

    def reflectivity_and_spectral_indices(self, image):

        # Select and rename relevant bands
        # Normalize optical bands to get reflectivity and clamp to [0,1]
        optical_bands = (image.select(self.optical_bands[0], self.optical_bands[1])
                         .multiply(0.0000275).add(-0.2).clamp(0, 1))
        albedo = optical_bands.select(['red', 'green', 'blue']).reduce(ee.Reducer.mean()).rename('albedo')
        optical_bands = optical_bands.addBands(albedo)
        # Convert thermal band to Celsius
        thermal_bands = (image.select(self.thermal_bands[0], self.thermal_bands[1])
                         .multiply(0.00341802).add(149).subtract(273.15))
        cloud_bit = 3
        dilation_bit = 1
        qa = image.select('QA_PIXEL')
        cloud = qa.bitwiseAnd(1 << cloud_bit).eq(2 ** cloud_bit).Or(
            qa.select('QA_PIXEL').bitwiseAnd(1 << dilation_bit).eq(2 ** dilation_bit)).rename('cloud')

        # Mask out saturated pixels
        saturation = image.select('QA_RADSAT').eq(0).rename('saturation')
        # "New" images of just counter, then append processed bands and update saturation
        image = image.addBands(ee.Image.constant(1).rename('counter')).select('counter')
        image = image.addBands(optical_bands).addBands(thermal_bands).addBands(cloud)  # .updateMask(saturation)

        dic = {'green': image.select('green'),
               'red': image.select('red'),
               'nir': image.select('nir'),
               'swir1': image.select('swir1')}
        image = image.addBands(image.expression('(green-swir1)/(green+swir1)', dic).rename('NDSI'))
        image = image.addBands(image.expression('(green-nir)/(green+nir)', dic).rename('NDWI'))
        image = image.addBands(image.expression('(nir-red)/(nir+red)', dic).rename('NDVI'))
        image = image.addBands(image.expression('(green ** 2)- (swir1**2)', dic).rename('MDSII'))

        # # Get image DOY for seasonal classification
        doy_band = ee.Image.constant(image.date().getRelative('day', 'year')).toInt16().rename('doy')
        image = image.addBands(doy_band)
        return image
