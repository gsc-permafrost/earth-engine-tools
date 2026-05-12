# -*- coding: utf-8 -*-
"""
download_from_ee
*DESCRIPTION*

Author: rparker
Created: 2026-04-15
"""


import time
import warnings
from pathlib import Path
import google_api_functions.google_drive as gd


def download_from_google_drive(task_list: list, google_folder: str, local_download_loc: str | Path,
                               extract_from_folder=False):
    if isinstance(local_download_loc, str):
        local_download_loc = Path(local_download_loc)
    num_complete = -1
    # print("Waiting for earth engine to complete processing tasks...")
    while True:
        task_status = {}
        for task in task_list:
            while True:
                try:
                    task_status[task.id] = task.status()["state"]
                except Exception as e:
                    warnings.warn(f"{type(e)}: {e}")
                    time.sleep(1)
                else:
                    break
        if num_complete != list(task_status.values()).count('COMPLETED'):
            num_complete = list(task_status.values()).count('COMPLETED')
            # print(f"{num_complete}/{len(task_status.values())} completed")
        if list(task_status.values())[0] == "COMPLETED" and len(set(task_status.values())) == 1:
            break
        if "FAILED" in list(task_status.values()):
            message = f"One of the tasks submitted to earth engine failed. Check the Google earth engine task manager" \
                      f" for details."
            raise RuntimeError(message)
        time.sleep(5)
    time.sleep(10)  # wait 10 seconds to ensure all files are done saving in the folder
    # downloading data from google drive
    # print("Downloading data...")
    if extract_from_folder:
        local_folder = local_download_loc
    else:
        local_folder = Path(local_download_loc, google_folder)
    local_folder.mkdir(exist_ok=True)
    gd.download_folder(google_folder=google_folder, save_folder=local_folder, delete_after=True)
    return local_folder
