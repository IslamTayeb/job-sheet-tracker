import os
import argparse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv
import pickle
import base64
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from datetime import datetime

# Load environment variables
load_dotenv()

# Gmail API scopes
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_gmail_service():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("gmail", "v1", credentials=creds)


def get_sheets_service():
    creds = None
    if os.path.exists("sheets_token.pickle"):
        with open("sheets_token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SHEETS_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("sheets_token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("sheets", "v4", credentials=creds)


def get_email_content(service, msg_id):
    message = (
        service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    )

    headers = message["payload"]["headers"]
    subject = next(
        header["value"] for header in headers if header["name"].lower() == "subject"
    )
    from_email = next(
        header["value"] for header in headers if header["name"].lower() == "from"
    )
    date = next(
        header["value"] for header in headers if header["name"].lower() == "date"
    )

    parts = message["payload"].get("parts", [])
    body = ""

    if parts:
        for part in parts:
            if part["mimeType"] == "text/plain":
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                break
    else:
        body = base64.urlsafe_b64decode(message["payload"]["body"]["data"]).decode(
            "utf-8"
        )

    return {"subject": subject, "from": from_email, "date": date, "body": body}


def append_to_sheets(service, spreadsheet_id, email_data):
    range_name = "Sheet1!A:D"  # Adjust based on your sheet structure
    values = [
        [
            email_data["date"],
            email_data["from"],
            email_data["subject"],
            email_data["body"][:50000],  # Truncate long emails
        ]
    ]

    body = {"values": values}

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def main():
    parser = argparse.ArgumentParser(
        description="Process Gmail emails to Google Sheets"
    )
    parser.add_argument(
        "--number", type=int, required=True, help="Number of latest emails to process"
    )
    args = parser.parse_args()

    # Get spreadsheet ID from environment variable
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not spreadsheet_id:
        raise ValueError("GOOGLE_SHEETS_ID environment variable not set")

    # Initialize services
    gmail_service = get_gmail_service()
    sheets_service = get_sheets_service()

    # Get latest emails
    results = (
        gmail_service.users()
        .messages()
        .list(userId="me", maxResults=args.number)
        .execute()
    )
    messages = results.get("messages", [])

    for message in messages:
        email_data = get_email_content(gmail_service, message["id"])
        append_to_sheets(sheets_service, spreadsheet_id, email_data)
        print(f"Processed email: {email_data['subject']}")


if __name__ == "__main__":
    main()
