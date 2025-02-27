import io
import os
import sys
import argparse
import json
import warnings
import google.generativeai as genai
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
import pickle
import base64
from datetime import datetime
import pytz
import time
import socket
import ssl
import logging


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("jobtrack")

logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
logging.getLogger("googleapiclient.discovery").setLevel(logging.WARNING)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GRPC_TRACE'] = 'none'
os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'
warnings.filterwarnings("ignore", message=".*file_cache is only supported.*")
stderr_backup = sys.stderr
sys.stderr = io.StringIO()
sys.stderr = stderr_backup

# Constants
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_RETRIES = 5
BATCH_SIZE = 5
API_RETRY_DELAY = 1
CONFIG_DIR = os.path.expanduser("~/.jobtrack")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
CREDS_FILE = os.path.join(CONFIG_DIR, "credentials.json")
GMAIL_TOKEN_FILE = os.path.join(CONFIG_DIR, "gmail_token.pickle")
SHEETS_TOKEN_FILE = os.path.join(CONFIG_DIR, "sheets_token.pickle")


def ensure_config_dir():
    """Ensure the config directory exists"""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    """Load configuration from config file"""
    ensure_config_dir()

    load_dotenv()

    config = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "google_sheets_id": os.getenv("GOOGLE_SHEETS_ID", ""),
    }

    # Load from config file if it exists
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved_config = json.load(f)
                config.update(saved_config)
        except Exception as e:
            logger.warning(f"Error loading config file: {e}")

    return config


def save_config(config):
    """Save configuration to config file"""
    ensure_config_dir()

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Configuration saved to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Error saving config file: {e}")
        raise


def save_credentials(creds_content):
    """Save Google API credentials to file"""
    ensure_config_dir()

    try:
        with open(CREDS_FILE, "w") as f:
            f.write(creds_content)
        logger.info(f"Credentials saved to {CREDS_FILE}")
    except Exception as e:
        logger.error(f"Error saving credentials file: {e}")
        raise


def retry_on_connection_error(func):
    def wrapper(*args, **kwargs):
        retries = 0
        while retries < MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except (socket.error, ssl.SSLError, HttpError) as e:
                retries += 1
                logger.warning(f"Connection error: {e}. Retry {retries}/{MAX_RETRIES}")
                if retries == MAX_RETRIES:
                    raise
                time.sleep(API_RETRY_DELAY * (2**retries))
        return func(*args, **kwargs)

    return wrapper


def setup_gemini():
    """Set up Google Gemini API client"""
    config = load_config()
    api_key = config.get("gemini_api_key")

    if not api_key:
        logger.error(
            "Gemini API key not found. Please set it with 'track config --gemini-api-key YOUR_KEY'"
        )
        sys.exit(1)

    genai.configure(api_key=api_key)
    generation_config = {
        "temperature": 0.0,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
    }
    return genai.GenerativeModel(
        "gemini-1.5-flash", generation_config=generation_config
    )


def get_gmail_service():
    """Get authenticated Gmail service"""
    creds = None
    if os.path.exists(GMAIL_TOKEN_FILE):
        with open(GMAIL_TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                logger.error(f"Google credentials not found at {CREDS_FILE}")
                logger.error(
                    "Please set up your Google credentials with 'track config --credentials'"
                )
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return build("gmail", "v1", credentials=creds)


def get_sheets_service():
    """Get authenticated Google Sheets service"""
    creds = None
    if os.path.exists(SHEETS_TOKEN_FILE):
        with open(SHEETS_TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                logger.error(f"Google credentials not found at {CREDS_FILE}")
                logger.error(
                    "Please set up your Google credentials with 'track config --credentials'"
                )
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SHEETS_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(SHEETS_TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return build("sheets", "v4", credentials=creds)


def extract_job_info_with_retry(model, email_content):
    """Extract job info from email content using Gemini AI"""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            prompt = f"""Extract the job position I applied to and company from this email. Include any ID numbers in the position. Otherwise, return "UNKNOWN" for both. If there's more than 1 mention of companies and one is a subsidary of the other, put the parent company first then in square brackets put the subsidary after the parent company. Put status as 0 if it's a rejection email, 1 if I've just applied, 2 if it's an online assessment, hirevue, or general screening survey, and 3 if it's an interview. Format the response as JSON with these exact keys: "position", "company", and "status" inside a code block. Ignore any irrelevant emails, promotional emails, or emails that don't contain job information. Make sure to ignore any email that isn't a job application or interview confirmation, even if those may contain JUST companies (e.g. New York Times or Medium articles that are ABOUT the job market or tech that aren't an actual job application).

            Email content:
            {email_content}"""

            response = model.generate_content(prompt)
            json_str = (
                response.text.split("```json\n")[1].split("\n```")[0]
                if "```json" in response.text
                else response.text
            )
            return json.loads(json_str)
        except Exception as e:
            retries += 1
            logger.warning(
                f"Error extracting job info: {e}. Retry {retries}/{MAX_RETRIES}"
            )
            if retries == MAX_RETRIES:
                return {"position": "UNKNOWN", "company": "UNKNOWN", "status": 1}
            time.sleep(API_RETRY_DELAY * (2**retries))


@retry_on_connection_error
def get_email_content(service, msg_id):
    """Get email content from Gmail API"""
    try:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )

        headers = message["payload"]["headers"]
        subject = next(
            (
                header["value"]
                for header in headers
                if header["name"].lower() == "subject"
            ),
            "",
        )
        from_email = next(
            (header["value"] for header in headers if header["name"].lower() == "from"),
            "",
        )
        date = next(
            (header["value"] for header in headers if header["name"].lower() == "date"),
            "",
        )

        date = date.replace(" (UTC)", "")
        try:
            parsed_date = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %z")
        except ValueError:
            try:
                parsed_date = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S")
                parsed_date = parsed_date.replace(tzinfo=pytz.UTC)
            except ValueError:
                parsed_date = datetime.now(pytz.UTC)

        est_tz = pytz.timezone("America/New_York")
        formatted_date = (
            parsed_date.astimezone(est_tz)
            .strftime("%m/%d/%y %H:%M")
            .replace(" EST", "")
        )

        def decode_body(part):
            if "body" in part and "data" in part["body"]:
                try:
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8"
                    )
                except:
                    return ""
            return ""

        body = ""
        payload = message["payload"]

        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    body = decode_body(part)
                    if body:
                        break
                elif "parts" in part:
                    for subpart in part["parts"]:
                        if subpart["mimeType"] == "text/plain":
                            body = decode_body(subpart)
                            if body:
                                break

        if not body and "body" in payload:
            body = decode_body(payload)

        email_content = f"""Subject: {subject}
From: {from_email}
Body: {body}"""

        model = setup_gemini()
        job_info = extract_job_info_with_retry(model, email_content)
        return {
            "date": formatted_date,
            "position": job_info["position"],
            "company": job_info["company"],
            "status": job_info.get("status", 1),
        }
    except Exception as e:
        logger.error(f"Error processing email: {str(e)}")
        return {
            "date": datetime.now(pytz.timezone("America/New_York")).strftime(
                "%m/%d/%y %H:%M"
            ),
            "position": "UNKNOWN",
            "company": "UNKNOWN",
            "status": 1,
        }


@retry_on_connection_error
def get_existing_entries(sheets_service, spreadsheet_id):
    """Get existing entries from Google Sheets"""
    try:
        result = (
            sheets_service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range="Sheet1!B:C")
            .execute()
        )

        existing = set()
        if "values" in result:
            for row in result.get("values", []):
                if len(row) >= 2:
                    existing.add(f"{row[0]}_{row[1]}")
        return existing
    except Exception as e:
        logger.error(f"Error getting existing entries: {str(e)}")
        return set()


@retry_on_connection_error
def append_to_sheets(service, spreadsheet_id, email_data):
    """Append data to Google Sheets"""
    values = [
        [
            email_data["date"],
            email_data["position"],
            email_data["company"],
            email_data["status"],
        ]
    ]

    body = {"values": values}
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A:D",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def prompt_for_missing_info(email_data):
    """Prompt user for missing job information"""
    if email_data["position"] != "UNKNOWN" and email_data["company"] != "UNKNOWN":
        return email_data

    print(f"Partial info detected:")
    print(f"Position: {email_data['position']}")
    print(f"Company: {email_data['company']}")

    if email_data["position"] == "UNKNOWN":
        user_input = input("Enter position (or 'n' to skip): ")
        if user_input.lower() != "n":
            email_data["position"] = user_input

    if email_data["company"] == "UNKNOWN":
        user_input = input("Enter company (or 'n' to skip): ")
        if user_input.lower() != "n":
            email_data["company"] = user_input

    return email_data


def process_emails(num_emails):
    """Process a number of recent emails and extract job information"""
    config = load_config()
    spreadsheet_id = config.get("google_sheets_id")

    if not spreadsheet_id:
        logger.error(
            "Google Sheets ID not set. Please set it with 'track config --sheets-id YOUR_ID'"
        )
        sys.exit(1)

    gmail_service = get_gmail_service()
    sheets_service = get_sheets_service()
    existing_entries = get_existing_entries(sheets_service, spreadsheet_id)

    results = (
        gmail_service.users()
        .messages()
        .list(userId="me", maxResults=num_emails)
        .execute()
    )
    messages = results.get("messages", [])

    if not messages:
        print("No emails found.")
        return

    print(f"Processing {len(messages)} emails...")

    for i, msg in enumerate(messages):
        try:
            print(f"Processing email {i + 1}/{len(messages)}...")
            email_data = get_email_content(gmail_service, msg["id"])

            if (
                email_data["position"] == "UNKNOWN"
                and email_data["company"] == "UNKNOWN"
            ):
                print("⚠️ Unable to extract info from email")
                continue

            if (
                email_data["position"] == "UNKNOWN"
                or email_data["company"] == "UNKNOWN"
            ):
                email_data = prompt_for_missing_info(email_data)
                if (
                    email_data["position"] == "UNKNOWN"
                    or email_data["company"] == "UNKNOWN"
                ):
                    print("⚠️ Skipping email with missing information")
                    continue

            entry_key = f"{email_data['position']}_{email_data['company']}"
            if entry_key in existing_entries:
                print(
                    f"ℹ️ Skipping duplicate: {email_data['position']} at {email_data['company']}"
                )
                continue

            existing_entries.add(entry_key)
            append_to_sheets(sheets_service, spreadsheet_id, email_data)

            status_map = {0: "Rejected", 1: "Applied", 2: "Assessment", 3: "Interview"}
            status_text = status_map.get(email_data["status"], "Unknown")

            print(
                f"✓ Added: {email_data['position']} at {email_data['company']} - Status: {email_data['status']} ({status_text})"
            )

        except Exception as e:
            logger.error(f"Error processing email {i + 1}: {str(e)}")

        time.sleep(API_RETRY_DELAY)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    print(f"Processing complete. View your Google Sheet: \033[4m{sheet_url}\033[0m")


def config_command(args):
    """Handle configuration command"""
    config = load_config()

    if args.gemini_api_key:
        config["gemini_api_key"] = args.gemini_api_key
        save_config(config)
        print(f"Gemini API key updated.")

    if args.sheets_id:
        config["google_sheets_id"] = args.sheets_id
        save_config(config)
        print(f"Google Sheets ID updated.")

    if args.credentials:
        # Check if the input is a file path or a JSON string
        if os.path.exists(args.credentials):
            # It's a file path
            with open(args.credentials, "r") as f:
                creds_content = f.read()
            save_credentials(creds_content)
            print(f"Google API credentials updated from {args.credentials}.")
        else:
            try:
                json.loads(args.credentials)
                save_credentials(args.credentials)
                print("Google API credentials updated.")
            except json.JSONDecodeError:
                print("Error: Invalid JSON format. Credentials not updated.")
                sys.exit(1)

    if args.credentials_input:
        print("Please paste your Google API credentials JSON content:")
        print("(Press Ctrl+D when finished)")

        creds_lines = []
        try:
            while True:
                line = input()
                creds_lines.append(line)
        except EOFError:
            creds_content = "\n".join(creds_lines)

        try:
            # Validate it's proper JSON
            json.loads(creds_content)
            save_credentials(creds_content)
            print("Google API credentials updated.")
        except json.JSONDecodeError:
            print("Error: Invalid JSON format. Credentials not updated.")
            sys.exit(1)

    if not (
        args.gemini_api_key
        or args.sheets_id
        or args.credentials
        or args.credentials_input
    ):
        print("Current Configuration:")
        print(f"Gemini API Key: {'Set' if config.get('gemini_api_key') else 'Not set'}")
        print(f"Google Sheets ID: {config.get('google_sheets_id') or 'Not set'}")
        print(
            f"Google API Credentials: {'Exists' if os.path.exists(CREDS_FILE) else 'Not set'}"
        )
        print("\nUse 'track config --help' for configuration options.")


def main_cli():
    if len(sys.argv) == 2 and sys.argv[1].isdigit():
        num_emails = int(sys.argv[1])
        if num_emails <= 0:
            print("Number of emails must be positive")
            sys.exit(1)
        process_emails(num_emails)
        return

    parser = argparse.ArgumentParser(description="Job Application Tracker")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    process_parser = subparsers.add_parser(
        "process", help="Process emails to find job applications"
    )
    process_parser.add_argument(
        "number", type=int, help="Number of latest emails to process"
    )

    # Config command
    config_parser = subparsers.add_parser("config", help="Configure settings")
    config_parser.add_argument("--gemini-api-key", help="Set your Gemini API key")
    config_parser.add_argument("--sheets-id", help="Set your Google Sheets ID")
    config_parser.add_argument(
        "--credentials",
        help="Google API credentials (either as a JSON string or path to credentials.json file)",
    )
    config_parser.add_argument(
        "--credentials-input",
        action="store_true",
        help="Input Google API credentials interactively",
    )

    args = parser.parse_args()

    # Handle different commands
    if args.command == "process":
        if args.number <= 0:
            print("Number of emails must be positive")
            sys.exit(1)
        process_emails(args.number)
    elif args.command == "config":
        config_command(args)
    else:
        parser.print_help()


def main():
    parser = argparse.ArgumentParser(
        description="Process Gmail emails to Google Sheets"
    )
    parser.add_argument(
        "--number", type=int, required=True, help="Number of latest emails to process"
    )
    args = parser.parse_args()

    process_emails(args.number)


if __name__ == "__main__":
    main_cli()
