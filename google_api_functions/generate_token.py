# -*- coding: utf-8 -*-
"""
*DESCRIPTION*

Author: rparker
Created: 2023-04-17
"""

import os
from google_api_functions.create_service import create_service

SECRET_JSON = os.path.join(os.path.dirname(__file__), "client_secret_google_oauth.json")
API_NAME = "drive"
API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN = os.path.join(os.path.dirname(__file__), "token.json")


def generate_token():
    try:
        service = create_service(SECRET_JSON, API_NAME, API_VERSION, SCOPES)
        return
    except:
        if os.path.exists(TOKEN):
            os.remove(TOKEN)
        service = create_service(SECRET_JSON, API_NAME, API_VERSION, SCOPES)
    return



