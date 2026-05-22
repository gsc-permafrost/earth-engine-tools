# -*- coding: utf-8 -*-
"""
ee_aufeis_identification
EEAufeisIdentification class and it's parents serves as a backend to contain the methods and defaults for aufeis work
Developed in collaboration by Peter Morse, Ryan Parker, and June Skeeter
Can be run in a jupyter notebook for interactive work or as a standalone for automated procedures

Author: rparker
Created: 2026-04-13
"""

import ee
import datetime as dt
from pathlib import Path
import numpy as np

from .landsat_collection import LandsatCollection
from .download_from_google_drive import download_from_google_drive


class EEAufeisIdentification(LandsatCollection):
    def __init__(self, project_name: str, aoi: list[list[float]], start_year: int, end_year: int, start_doy: int,
                 end_doy: int, satellites: list[int] = [5, 7, 8, 9], cloud_frac: int = 50, clip_to_aoi: bool = False):

        super().__init__(project_name=project_name,
                         aoi=aoi,
                         start_doy=start_doy,
                         end_doy=end_doy,
                         satellites=satellites,
                         cloud_frac=cloud_frac,
                         start_year=start_year,
                         end_year=end_year)
        self.clip_to_aoi = clip_to_aoi
        # self.investigation_start_year = start_year
        # self.investigation_end_year = end_year

        # For cloud/water masks
        self.ndsi_masking_threshold = 0.4
        self.mdsii_masking_threshold = 0.144
        self.nir_wet_snow_threshold = 0.4
        self.ndwi_masking_threshold = 0.2
        self.ndvi_masking_threshold = 0.3
        self.albedo_masking_threshold = 0.3
        self.thermal_threshold = 2.5
        self.summer_start_doy = 180
        self.water_score_threshold = 0.4
        self.water_buffer_count = 3

        # for aufeis identification
        self.spatial_filter_bands = ["snow", "wet_snow_ndwi_score"]
        self.output_pixel_size_m = 30

        # scale to 480 m pixels -> 5.7 km radius kernel
        self.downsample_scaling_factor = 16
        self.kernel_size = 12 * self.downsample_scaling_factor * self.output_pixel_size_m
        self.kernel_units = "meters"

        self.snow_threshold = 0.05
        self.wet_snow_threshold = 0

        # for data export and download
        self.crs = "EPSG:3979"
        self.tile_size_px = 1500

        self.collection = self.collection.map(self.image_classification)

        self.imagery_water_mask = None
        self.create_imagery_water_mask()

        self.aufeis = None
        self.identify_aufeis()
        return

    def generate_tiling_grid(self) -> ee.FeatureCollection:
        """
        Generates a tiling grid feature collection based on the bounds of self.aoi or self.collection. The export grid
        is intended to be used to split the image into multiple smaller export tasks instead of one massive one.

        :return: an earth engine feature collection (ee.FeatureCollection) representing the tiling grid
        """
        tile_dimension = self.output_pixel_size_m * self.tile_size_px

        # Use AOI if clipping, otherwise collection bounds
        bounding_box = ee.Algorithms.If(condition=self.clip_to_aoi,
                                        trueCase=self.aoi.bounds(proj=self.crs, maxError=1),
                                        falseCase=self.collection.geometry().bounds(proj=self.crs, maxError=1))

        bounding_box = ee.Geometry(bounding_box)
        bbox_coords = ee.Array.cat(bounding_box.coordinates(), 1)
        x_min = ee.Number(bbox_coords.slice(1, 0, 1).reduce('min', [0]).get([0, 0]))
        y_min = ee.Number(bbox_coords.slice(1, 1, 2).reduce('min', [0]).get([0, 0]))
        x_max = ee.Number(bbox_coords.slice(1, 0, 1).reduce('max', [0]).get([0, 0]))
        y_max = ee.Number(bbox_coords.slice(1, 1, 2).reduce('max', [0]).get([0, 0]))

        x_diff = x_max.subtract(x_min)
        y_diff = y_max.subtract(y_min)

        # Small case (single tile)
        def make_single_tile():
            vertices = ee.List([[x_min, y_min],
                                [x_max, y_min],
                                [x_max, y_max],
                                [x_min, y_max],
                                [x_min, y_min]])
            return ee.FeatureCollection([ee.Feature(ee.Geometry.Polygon(coords=vertices, proj=self.crs, evenOdd=False),
                                                    {"id": "tile_0", "value": 0})])

        # Multi-tile case
        def make_grid():
            ll_padding = 1

            lower_left_x = x_min.divide(self.output_pixel_size_m).int().subtract(ll_padding).multiply(
                self.output_pixel_size_m)
            lower_left_y = y_min.divide(self.output_pixel_size_m).int().subtract(ll_padding).multiply(
                self.output_pixel_size_m)

            x_range = x_max.subtract(lower_left_x)
            y_range = y_max.subtract(lower_left_y)

            num_tiles_x = x_range.divide(tile_dimension).int().add(1)
            num_tiles_y = y_range.divide(tile_dimension).int().add(1)

            x_indices = ee.List.sequence(0, num_tiles_x.subtract(1))
            y_indices = ee.List.sequence(0, num_tiles_y.subtract(1))

            def make_column(ix):
                ix = ee.Number(ix)

                def make_tile(iy):
                    iy = ee.Number(iy)

                    left = lower_left_x.add(ix.multiply(tile_dimension))
                    bottom = lower_left_y.add(iy.multiply(tile_dimension))
                    right = left.add(tile_dimension)
                    top = bottom.add(tile_dimension)

                    coords = ee.List([[left, bottom],
                                      [right, bottom],
                                      [right, top],
                                      [left, top],
                                      [left, bottom]])

                    tile_id = ix.multiply(num_tiles_y).add(iy)

                    return ee.Feature(ee.Geometry.Polygon(coords=coords, proj=self.crs, evenOdd=False),
                                      {"id": tile_id.format("tile_%d"), "value": tile_id})
                return y_indices.map(make_tile)
            tiles = x_indices.map(make_column).flatten()

            return ee.FeatureCollection(tiles).filter(ee.Filter.intersects('.geo', bounding_box))

        return ee.FeatureCollection(ee.Algorithms.If(condition=x_diff.lt(tile_dimension).And(y_diff.lt(tile_dimension)),
                                                     trueCase=make_single_tile(),
                                                     falseCase=make_grid()))

    def download_aufeis_data(self, download_dir: str | Path, dry_run: bool = False) -> ee.FeatureCollection:
        """
        compiles the relevent data in self.aufeis_investigation_years into a single image, submits an export task, waits
        for the export to complete, then downloads the data from google drive.

        :param download_dir: the directory where the data will be saved

        :param dry_run: if true export task and download will be skipped. Useful when working in Jupyter Notebook and
        want to visualize the would-be export data

        :param clip_to_aoi: if true the image will be clipped to the extent of self.aoi prior to export

        :return: output image: the image which has been submitted for export

        :return: filtered_grid: tiling grid feature collection returned by 'generate_tiling_grid'
        """

        #  generate tiling grid
        filtered_grid = self.generate_tiling_grid()
        if dry_run:
            return filtered_grid

        # for each tile and image submit an export task
        google_folder = f"aufeis_data_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}"

        grid_size = filtered_grid.size().getInfo()
        feature_list = filtered_grid.toList(grid_size)

        zeros = ee.Image.constant(0).rename("zeros")
        water_mask = zeros.where(self.imagery_water_mask.select("water_mask").eq(1), 1).int().rename("water_mask")
        terrain_mask = zeros.where(self.combined_terrain_mask.eq(1), 1).int().rename("terrain_mask")

        task_list = list()
        for i in range(grid_size):
            feature = ee.Feature(feature_list.get(i))
            geometry = feature.geometry()
            for year, image in self.aufeis.items():
                output_image = image.select("aufeis").multiply(4).int().rename(f"aufeis_{year}")
                output_image = output_image.addBands(image.select("data_present").int().rename(f"pixel_counts_{year}"))
                if year == self.start_year:
                    output_image = output_image.addBands(water_mask).addBands(terrain_mask)
                task_name = f"y{year}_tile_{i}"
                task = ee.batch.Export.image.toDrive(image=output_image,   # .unmask(99),
                                                     description=task_name,
                                                     fileNamePrefix=task_name,
                                                     fileFormat='GeoTIFF',
                                                     folder=google_folder,
                                                     crs=self.crs,
                                                     scale=self.output_pixel_size_m,
                                                     region=geometry,
                                                     maxPixels=int(1e10))
                task.start()
                task_list.append(task)

        # wait for all tasks to complete then download the data
        download_from_google_drive(task_list=task_list,
                                   google_folder=google_folder,
                                   local_download_loc=download_dir,
                                   extract_from_folder=True)
        return filtered_grid

    def image_classification(self, image):
        # Get bands and apply classification logic
        # 1: ndsi > threshold = snow; except where albedo < threshold
        # 1/2: 0 < ndsi < threshold = wet/melting snow
        # high ndsi but low alebeo assumed to be a false positive for snow, common over very dark water surfaces
        ndsi_classified = image.select('NDSI').gt(self.ndsi_masking_threshold).int()
        mdsii_classified = image.select('MDSII').gt(self.mdsii_masking_threshold).int()
        nir_classified = image.select('nir').gt(self.nir_wet_snow_threshold).int()
        ndwi_classified = image.select('NDWI').lt(0.2).And(image.select("NDWI").gt(0)).int()

        snow = ndsi_classified.And(mdsii_classified).rename('snow')
        # snow = snow.where(snow.eq(0).And(ndsi_classified.Or(mdsii_classified)), 0.5)
        snow = snow.where(snow.eq(0).And(image.select('NDSI').gt(0).And(image.select('MDSII').gt(0))), 0.5)

        # snow = image.select('NDSI').gt(self.ndsi_masking_threshold).int().rename('snow')
        # snow = snow.where(snow.eq(0).And(image.select('NDSI').gt(0)), 0.5)

        dark = image.select('albedo').lt(self.albedo_masking_threshold).int()
        snow = snow.where(dark, 0)

        wet_snow_nir = snow.gt(0).And(nir_classified).rename('wet_snow_nir')
        wet_snow_ndwi = snow.gt(0).And(ndwi_classified).rename('wet_snow_ndwi')
        wet_snow_ndwi_score = wet_snow_ndwi.where(wet_snow_ndwi.eq(1), snow).rename('wet_snow_ndwi_score')
        wet_snow_nir_score = wet_snow_nir.where(wet_snow_nir.eq(1), snow).rename('wet_snow_nir_score')
        image = image.addBands(snow)
        image = image.addBands(wet_snow_nir).addBands(wet_snow_ndwi).addBands(wet_snow_ndwi_score).addBands(
            wet_snow_nir_score)

        # clouds from QA_Pixel
        # un-flag snow = 1 pixels and warm pixels (lw>threshold)
        # snow and warm pixels assumed to be false positives for clouds
        # The add cloud flag for bright areas not classified as snow
        cloud = image.select('cloud')
        warm = image.select('lwir').gt(self.thermal_threshold).int()
        light = image.select('albedo').gte(self.albedo_masking_threshold).int()
        cloud = cloud.where(snow.eq(1), 0).where(warm, 0)
        cloud = cloud.where(light.And(snow.eq(0)), 1)
        # add cloud flags for light non-snow areas
        image = image.addBands(srcImg=cloud, names=None, overwrite=True)

        # if not also flagged as snow
        # 1: ndwi > threshold = water
        # 1/2: 0 < ndwi < threshold = wetland
        # separate "water_feature" class for summer to identify "permanent" water features
        # count cloud-free summer days for generating cloud score
        water = image.select('NDWI').gt(self.ndwi_masking_threshold).int().rename('water')
        water = water.where(water.eq(0).And(image.select('NDWI').gt(0)), 0.5)
        water = water.where(snow, 0)
        image = image.addBands(water)

        # ID vegetation for extra context
        # defer to snow and water flags first
        vegetation = image.select('NDVI').gt(self.ndvi_masking_threshold).int().rename('vegetation')
        vegetation = vegetation.where(snow, 0).where(water.gt(0), 0)
        image = image.addBands(vegetation)

        # dry, snow-free land surfaces
        dry_snow_free = image.select('NDWI').lt(0).And(image.select('NDSI').lt(0)).int().rename('dry_snow_free')
        dry_snow_free = dry_snow_free.where(cloud, 0)
        image = image.addBands(dry_snow_free)

        # Other class to catch all pixels not otherwise identified
        other = snow.eq(0).And(water.eq(0)).And(cloud.eq(0)).And(vegetation.eq(0)).And(dry_snow_free.eq(0)).rename(
            'other')
        image = image.addBands(other)
        return image

    # Spatial Filtering
    def change_resolution(self, image):
        max_pixels = int(np.square(self.downsample_scaling_factor + 1))
        resolution = self.downsample_scaling_factor * self.output_pixel_size_m
        if max_pixels > 65536:
            max_pixels = 65536
            print('Warning: Resolution reduction is too coarse, relying on bestEffort=True should produce usable '
                  'results but may reduce precisions')

        projection = image.select(self.spatial_filter_bands[0]).projection()
        selection = image.select(self.spatial_filter_bands,
                                 [f"{b}_{resolution}" for b in self.spatial_filter_bands])
        if self.downsample_scaling_factor % 2 != 0:
            raise ValueError("not divisible by 2")
        if self.downsample_scaling_factor / 2 > 9:
            raise ValueError("too large")

        down_sampled = (selection.reduceResolution(reducer=ee.Reducer.mean(),
                                                   maxPixels=max_pixels,
                                                   bestEffort=True)
                        .reproject(crs=projection, scale=resolution))
        return image.addBands(down_sampled)

    def kernel_filter(self, image):
        resolution = self.downsample_scaling_factor * self.output_pixel_size_m
        selection = image.select([f"{b}_{resolution}" for b in self.spatial_filter_bands])
        reduced_image = selection.reduceNeighborhood(reducer=ee.Reducer.mean(),
                                                     kernel=ee.Kernel.circle(
                                                         radius=self.kernel_size,
                                                         units=self.kernel_units,
                                                         normalize=False))
        return image.addBands(reduced_image)

    def rescale(self, image):
        projection = image.select(self.spatial_filter_bands[0]).projection()
        return image.reproject(crs=projection, scale=self.output_pixel_size_m)

    def spatial_filter(self, collection: ee.ImageCollection = None):
        if collection is None:
            collection = self.collection

        # Downsampling spatial resolution to circumvent limits (512 pixels) on kernel size
        collection = collection.map(self.change_resolution)
        if self.kernel_size is not None:
            collection = collection.map(self.kernel_filter)
        self.collection = self.collection.map(self.rescale)
        return collection

    def identify_aufeis(self):
        """
        populates self.interannual_aufeis and self.aufeis_investigation_years based on the data in self.collection

        self.aufeis_investigation_years: a dictionary of yearly aufeis idata
            keys: the years between self.investigation_start_year and self.investigation_end_year (inclusive)
            values: an image of the pixels flaggged as wet snow for the corresponding year:
                bands:
                aufeis: The sum of wet_snow_ndwi_score from all images within that year. Any values greater than 1 are
                clamped to 1.25. Possible values are 0, 0.5, 1, and 1.25. 1.25 represents pixels which
                were classed as wet snow (1) and/or potential wet snow (0.5) in more than one image.

                flagged_as_wet_snow: a binary image representing where non-zero data is present in the 'aufeis' band

                data_present: a binary image representing where data is present in the 'aufeis' band

                constrained_aufeis: the 'aufeis' constrained to where the 'interannual_aufeis' is 1

        self.interannual_aufeis: an image showing the location of pixels which have been consistently flagged as wet
        snow over multiple years between 1985 and present
            bands:
            total_aufeis: the sum the 'aufeis' bands for all years (1985 - present)

            years_flagged_as_wet_snow: the sum the 'flagged_as_wet_snow' bands for all years (1985 - present)

            years_with_data: the sum the 'data_present' bands for all years (1985 - present)

            interannual_aufeis: a binary image where pixels had a mean aufeis value greater than 0.6 and 4 or more
            years of data were present
        """

        # ee.Image.map() functions
        def apply_cloud_mask(img):
            """mask out cloud"""
            return img.updateMask(img.select("cloud").Not())

        def apply_gsw_water_mask(img):
            """mask out GSW water"""
            return img.updateMask(self.gsw_water_mask.focalMax(2.5).Not())

        def apply_imagery_water_mask(img):
            """mask out water flagged in imagery"""
            return img.updateMask(self.imagery_water_mask.select("water_mask").Not())

        def mask_too_snowy_and_no_wet_snow(img):
            """
            based on spatial filter bands
            mask out regions where 5% or more of the pixels are snow
            mask out regions where no wet snow is present
            """
            resolution = self.downsample_scaling_factor * self.output_pixel_size_m
            minimal_snow = img.select(f"snow_{resolution}_mean").lt(self.snow_threshold)
            wet_snow_present = img.select(f"wet_snow_ndwi_score_{resolution}_mean").gt(self.wet_snow_threshold)
            return img.updateMask(minimal_snow).updateMask(wet_snow_present)

        def apply_terrain_mask(img):
            return img.updateMask(self.combined_terrain_mask)

        #  calculate single year aufeis information and add it to self.aufeis_investigation_years if necessary
        self.aufeis = dict()
        for year in range(self.start_year, self.end_year + 1):
            # extract relevant bands to a working image collection and apply water/cloud masks
            year_collection = (self.collection.select(["snow", "wet_snow_ndwi_score", "cloud", "water"])
                               .filter(ee.Filter.calendarRange(year, year, 'year')))
            year_collection = year_collection.map(apply_cloud_mask).map(apply_imagery_water_mask)
            # add spatial filter bands
            year_collection = self.spatial_filter(collection=year_collection)
            # add terrain mask and spatial filter mask
            year_collection = year_collection.map(apply_terrain_mask).map(mask_too_snowy_and_no_wet_snow)

            single_year_aufeis = (year_collection.select("wet_snow_ndwi_score").sum().clamp(0, 1.25)
                                  .rename("aufeis"))
            single_year_aufeis = single_year_aufeis.addBands(
                single_year_aufeis.select("aufeis").gt(0).int().rename("flagged_as_wet_snow"))
            single_year_aufeis = single_year_aufeis.addBands(
                single_year_aufeis.select("aufeis").multiply(0).add(1).int().rename("data_present"))
            self.aufeis[year] = single_year_aufeis
        return

    def create_imagery_water_mask(self):

        # Modified NDWI from Xu, 2006
        def norm_diff_green_swir1(img):
            dic = {'green': img.select('green'),
                   'swir1': img.select('swir1')}
            img = img.addBands(img.expression('(green-swir1)/(green+swir1)', dic).rename('NDGS1I'))
            img = img.addBands(img.select("NDGS1I").gt(-0.15).rename('NDGS1I_class'))
            return img

        """
        def norm_diff_green_swir2(img):
            dic = {'green': img.select('green'),
                   'swir2': img.select('swir2')}
            img = img.addBands(img.expression('(green-swir2)/(green+swir2)', dic).rename('NDGS2I'))
            img = img.addBands(img.select("NDGS2I").gt(0).rename('NDGS2I_class'))
            return img
        """

        warm_season = (
            self.collection.filter(ee.Filter.calendarRange(self.summer_start_doy, self.end_doy, 'day_of_year'))
            .select(["swir1", "swir2", "green"]))
        warm_season = warm_season.map(norm_diff_green_swir1)

        self.imagery_water_mask = warm_season.select("NDGS1I_class").mean().rename("water_score")
        self.imagery_water_mask = self.imagery_water_mask.addBands(
            self.imagery_water_mask.gt(0.3).focalMax(2.5).rename("water_mask"))
        return
