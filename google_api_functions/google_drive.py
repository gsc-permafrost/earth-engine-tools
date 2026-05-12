import io
import time
from warnings import warn
from googleapiclient.http import MediaIoBaseDownload
from pathlib import Path

from google_api_functions.create_service import create_service
from google_api_functions.generate_token import generate_token

SECRET_JSON = Path(Path(__file__).parent, "client_secret_google_oauth.json")
API_NAME = "drive"
API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def download_folder(google_folder: str, save_folder: str | Path, delete_after=False):
    if isinstance(save_folder, str):
        save_folder = Path(save_folder)
    save_folder.mkdir(exist_ok=True)
    c = 0
    while True:
        try:
            service = create_service(SECRET_JSON, API_NAME, API_VERSION, SCOPES)
            break
        except:
            generate_token()
            time.sleep(5)
            c += 1
    folder_ids = []
    while True:
        prev_length = len(folder_ids)
        response = service.files().list(q=f"name = '{google_folder}'").execute()
        for obj in response["files"]:
            if obj["id"] not in folder_ids:
                folder_ids.append(obj["id"])
        if prev_length == len(folder_ids):
            break

    query = ""
    for fid in folder_ids:
        if query == "":
            query = f"parents = '{fid}'"
        else:
            query = f"{query} or parents = '{fid}'"

    response = service.files().list(q=query).execute()
    files = {}
    for obj in response["files"]:
        files[obj["id"]] = obj["name"]
    for key in files:
        request = service.files().get_media(fileId=key)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fd=fh, request=request)

        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        with open(Path(save_folder, files[key]), "wb") as f:
            f.write(fh.read())
            f.close()
    if delete_after:
        for fid in folder_ids:
            delete_success = False
            for i in range(5):
                try:
                    service.files().delete(fileId=fid).execute()
                    delete_success = True
                    break
                except:
                    time.sleep(5)
            if not delete_success:
                warn(f"{google_folder} not deleted from google drive.")
        while True:
            response = service.files().list(q=f"name = '{google_folder}'").execute()
            if len(response["files"]) == 0:
                break
            for obj in response["files"]:
                service.files().delete(fileId=obj["id"]).execute()
    return


def create_folder(new_folder):
    while True:
        try:
            service = create_service(SECRET_JSON, API_NAME, API_VERSION, SCOPES)
            break
        except:
            time.sleep(5)
            pass
    folder_meta = {'name': new_folder, 'mimeType': 'application/vnd.google-apps.folder'}
    service.files().create(body=folder_meta, fields='id').execute()
    return

