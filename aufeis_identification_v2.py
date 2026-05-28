# -*- coding: utf-8 -*-
"""
aufeis_identification_v2
*DESCRIPTION*

Author: rparker
Created: 2026-04-15
"""

from pathlib import Path
import yaml
import geopandas as gpd
import warnings

from ee_processing import EEAufeisIdentification
import local_processing as lp


def main():
    input_param_yaml = Path(Path(__file__).parent, "input_params.yaml")
    with open(input_param_yaml, 'r') as file:
        input_param_dict = yaml.safe_load(file)

    # input params
    working_dir = Path(input_param_dict["working_dir"])
    aoi = input_param_dict["aoi"]
    start_year = input_param_dict["start_year"]
    end_year = input_param_dict["end_year"]
    cut_off_value = input_param_dict["cut_off_value"]
    clip_to_aoi = input_param_dict["clip_to_aoi"]
    ee_project = input_param_dict["ee_project"]
    print(working_dir)

    # establish output directories
    download_dir = Path(working_dir, "downloaded_data")
    interannual_dir = Path(working_dir, "interannual_constraint")
    vectorized_dir = Path(working_dir, "vectorized")
    output_dir = Path(working_dir, "compiled_aufeis")
    for dir_path in [download_dir, vectorized_dir, output_dir, interannual_dir]:
        dir_path.mkdir(exist_ok=True, parents=True)

    if not ("local_only" in input_param_dict and input_param_dict["local_only"]):
        # create GEE layers
        aufeis = EEAufeisIdentification(project_name=ee_project,
                                        aoi=aoi,
                                        start_year=start_year,
                                        end_year=end_year,
                                        start_doy=100,
                                        end_doy=240,
                                        satellites=[5, 7, 8, 9],
                                        cloud_frac=50,
                                        clip_to_aoi=clip_to_aoi)
        # submit GEE export tasks and download data from google drive
        aufeis.download_aufeis_data(download_dir=download_dir)
    else:
        print("Skipping GEE tasks, working off preexisting data.")

    # vectorize all bands in downloaded imagery and compile one vector file per band
    lp.vectorize_gee_export(download_dir, vectorized_dir)

    # constrain aufeis GEE outputs to where interannual aufeis features form
    # lp.interannual_aufeis_constraint(vectorized_dir)

    # remove non-aufeis features from yearly aufeis datasets and perform lone-pixel filtering
    aufeis_datasets = vectorized_dir.glob("aufeis_*.geojson")
    # aufeis_datasets = vectorized_dir.glob("constrained_aufeis_*.geojson")

    year_aufeis_data = dict()
    for aufeis_data_path in aufeis_datasets:
        year = aufeis_data_path.stem.split("_")[-1]
        aufeis_data = gpd.read_file(aufeis_data_path)
        aufeis_data = aufeis_data.loc[aufeis_data["pixel_value"] != 0]
        aufeis_data["area_m"] = aufeis_data.area
        aufeis_data = lp.small_or_low_value_filtering(aufeis_data)
        aufeis_data.rename(columns={"pixel_value": f"y_{year}"}, inplace=True)
        year_aufeis_data[year] = aufeis_data

    # union yearly aufeis datasets into one dataset
    compiled_aufeis = None
    for year, dataset in year_aufeis_data.items():
        if compiled_aufeis is None:
            compiled_aufeis = dataset[[f"y_{year}", "geometry"]]
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                compiled_aufeis = (compiled_aufeis.overlay(dataset[[f"y_{year}", "geometry"]], how="union")
                                   .explode().reset_index(drop=True))
    compiled_aufeis["area_m"] = compiled_aufeis.area

    # calculate return frequency
    compiled_aufeis["frequency"] = 0
    for year_col in [c for c in compiled_aufeis.columns if c.startswith("y_")]:
        compiled_aufeis[year_col] = compiled_aufeis[year_col].fillna(0)
        ix = compiled_aufeis.loc[compiled_aufeis[year_col] != 0].index
        compiled_aufeis.loc[ix, "frequency"] = compiled_aufeis.loc[ix, "frequency"] + 1

    # perform small-infrequent pixel filtering and aggregate features
    frequency_masked = lp.small_infrequent_pixel_filtering(
        data=compiled_aufeis, area_field="area_m", frequency_field="frequency")
    final_aufeis, aggregated_aufeis = lp.aggregate_aufeis(frequency_masked)

    # export final output
    final_aufeis.to_file(Path(output_dir, "compiled_aufeis.geojson"), driver="GeoJSON")
    final_aufeis.to_file(Path(output_dir, "compiled_aufeis.gdb"), layer="compiled_aufeis", driver="OpenFileGDB",
                         engine="pyogrio", layer_options={"TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER"})
    aggregated_aufeis.to_file(Path(output_dir, "aggregated_aufeis.geojson"), driver="GeoJSON")
    aggregated_aufeis.to_file(Path(output_dir, "compiled_aufeis.gdb"), layer="aggregated_aufeis",
                              driver="OpenFileGDB", engine="pyogrio",
                              layer_options={"TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER"})
    return


if __name__ == '__main__':
    main()
