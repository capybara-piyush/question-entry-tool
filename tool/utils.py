from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os
import pickle
import pandas as pd
import logging
from datetime import datetime

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def get_google_sheets_credentials():
    creds = None
    token_path = "token.pickle"
    credentials_path = "credentials.json"

    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    "credentials.json file not found. Please obtain it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return creds


def extract_sheet_id_from_url(url):
    if "spreadsheets/d/" in url:
        start_idx = url.find("spreadsheets/d/") + len("spreadsheets/d/")
        end_idx = url.find("/", start_idx)
        if end_idx == -1:
            end_idx = len(url)
        return url[start_idx:end_idx]
    raise ValueError("Invalid Google Sheets URL")


def read_google_sheet(sheet_url):
    try:
        sheet_id = extract_sheet_id_from_url(sheet_url)
        creds = get_google_sheets_credentials()
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        # Get all sheet names
        metadata = sheet.get(spreadsheetId=sheet_id).execute()
        sheets = metadata.get("sheets", [])

        all_data = {}
        for sheet_metadata in sheets:
            sheet_name = sheet_metadata["properties"]["title"]
            result = (
                sheet.values()
                .get(spreadsheetId=sheet_id, range=f"{sheet_name}!A:E")
                .execute()
            )
            values = result.get("values", [])

            if not values:
                continue

            df = pd.DataFrame(
                values[1:],
                columns=[
                    "Question",
                    "Correct",
                    "Incorrect1",
                    "Incorrect2",
                    "Incorrect3",
                ],
            )
            all_data[sheet_name] = df

        return all_data
    except Exception as e:
        raise Exception(f"Error reading Google Sheet: {str(e)}")


def setup_data_import_logger():
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"data_import_{timestamp}.log")

    logger = logging.getLogger("data_import")
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger, log_file
