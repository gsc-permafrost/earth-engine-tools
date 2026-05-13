# earth-engine-tools
A collection of functions and classes for processing, analyzing, and downloading data from Google Earth Engine. 
Originally developed to detect aufeis features across Canada's North using the Landsat archive.

### Setup
1. Clone the repository.
2. Create the project venv.
   - **Requires Python 3.12+**

   `python -m venv .venv`

   `.\.venv\Scripts\activate`

    `pip install -r requirements.txt`

3. Set up Google Earth Engine with your Google account.
4. Set up a project in Google Cloud, enable the Google Drive API, and download the OAuth client JSON.
   - Instructions can be found [here](https://www.youtube.com/watch?v=I5ili_1G0Vk).
5. Rename the OAuth client JSON to `client_secret_google_oauth.json` and copy it to the `google_api_functions`
   directory in the cloned repository.
6. Install and set up the GCloud CLI.
   - The installer can be downloaded [here](https://cloud.google.com/sdk/docs/install).

