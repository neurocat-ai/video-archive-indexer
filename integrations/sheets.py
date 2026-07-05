import os
import json
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SERVICE_ACCOUNT_FILE = str(
    BASE_DIR /
    os.getenv("GOOGLE_CREDENTIALS_FILE")
)

SPREADSHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID"
)

WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME")


def get_worksheet():
    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(
        SPREADSHEET_ID
    )

    return spreadsheet.worksheet(
        WORKSHEET_NAME
    )


def get_headers(sheet):
    headers = sheet.row_values(2)

    return [
        header.strip()
        for header in headers
        if header.strip()
    ]


def find_row_by_file_name(sheet, file_name):
    values = sheet.col_values(1)

    for index, value in enumerate(values, start=1):
        if value == file_name:
            return index

    return None


def format_transcript_segments(segments):
    rows = []

    for segment in segments:
        start = segment.get("start", 0)
        end = segment.get("end", 0)
        text = segment.get("text", "")

        rows.append(
            f"{start:.2f}-{end:.2f} | {text}"
        )

    return "\n".join(rows)


def normalize_value(column_name, value):
    if value is None:
        return ""

    if column_name == "transcript_segments":
        return format_transcript_segments(value)

    if isinstance(value, list):
        rows = []

        for item in value:
            if isinstance(item, dict):
                rows.append(
                    json.dumps(
                        item,
                        ensure_ascii=False
                    )
                )
            else:
                rows.append(str(item))

        return "\n".join(rows)

    if isinstance(value, dict):
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2
        )

    return str(value)


def upsert_video(data: dict):
    sheet = get_worksheet()
    headers = get_headers(sheet)

    file_name = data.get("file_name")

    if not file_name:
        raise ValueError("file_name is required")

    row_number = find_row_by_file_name(sheet, file_name)

    if not row_number:
        row_values = [
            normalize_value(header, data.get(header))
            for header in headers
        ]
        sheet.append_row(row_values)
        print(f"CREATED: {file_name}")
        return

    for column_index, header in enumerate(headers, start=1):
        if header not in data:
            continue

        cell = gspread.utils.rowcol_to_a1(row_number, column_index)
        value = normalize_value(header, data.get(header))

        sheet.update(cell, [[value]])

    print(f"UPDATED: {file_name} → row {row_number}")