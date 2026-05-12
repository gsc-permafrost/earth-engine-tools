# -*- coding: utf-8 -*-
"""
*DESCRIPTION*

Author: rparker
Created: 2022-08-15
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

token_path = os.path.join(os.path.dirname(__file__), "token.json")


def create_service(client_secret_file, api_name, api_version, *scopes):
    scopes_list = [scope for scope in scopes[0]]
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes_list)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, scopes_list)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    service = build(api_name, api_version, credentials=creds)
    return service
