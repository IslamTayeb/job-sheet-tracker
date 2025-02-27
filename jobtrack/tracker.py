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
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
warnings.filterwarnings("ignore", message=".*file_cache is only supported.*")


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
        "temperature": 0.25,
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
            prompt = f"""Extract the job position I applied to and company from this email. Include any ID numbers in the position. Pay special attention to email signatures, "From" lines, and domain names in email addresses as they often contain company names.

If you can't determine the position or company, return "UNKNOWN" for the missing field.

For company names:
- If there's more than 1 mention of companies and one is a subsidiary of the other, put the parent company first then in square brackets put the subsidiary after the parent company, like "Parent [Subsidiary]"
- If you see multiple companies and can't determine the relationship, choose the one most likely to be the actual employer
- Pay attention to email domains (company@example.com) as they often reveal the real company name
- Strip out any "talent acquisition" or "hiring" service names that aren't the actual employer

Put status as:
- 0 if it's a rejection email (looking for phrases like "moving forward with other candidates", "not selected", "unfortunately")
- 1 if I've just applied or received an application confirmation
- 2 if it's an online assessment, hirevue, coding challenge, or general screening survey
- 3 if it's an interview invitation or interview confirmation

Format the response as JSON with these exact keys: "position", "company", and "status" inside a code block.

Ignore any irrelevant emails, promotional emails, or emails that don't contain job information. Make sure to ignore any email that isn't a job application or interview confirmation, even if those may contain JUST companies (e.g. New York Times or Medium articles that are ABOUT the job market or tech that aren't an actual job application).

Examples:
<Example 1>
Email content:

Islam -

We think it's awesome that you chose to apply with us.  As you know, T-Mobile is changing the wireless industry for good.  And that means we're always listening to find out how we can do better.

Will you help us by taking a short survey to tell us about your experience applying for job requisition (REQ293888)? Your responses will have no impact on your candidacy.


ACCESSING THE SURVEY
If clicking on the link does not take you directly to the survey, please copy and paste the url into the address bar of your internet browser.
START THE SURVEY



NEED HELP?

For technical help while completing this survey, please visit our Support page.


Please click the link below if you would like to opt out of receiving further communications about this requisition ID:
Opt out
</Example 1>
<Analaysis 1>
This doesn't count as an application, it's a survey. The position is "UNKNOWN" and the company is "UNKNOWN" and is ultimately ignored because it's not a job/internship application even if it's associated with T-Mobile.
</Analysis 1>

<Example 2>
Subject:Point72 Employment Application - thanks!
From: talent@cubistsystematic.com
Body: Hi Islam,

Thanks for submitting your application for Quantitative Research Intern and your interest in the firm.

Our team will review your application and we will be in touch if your skills and experience are a good fit for this or any other roles that are currently open.
</Example 2>
<Analysis 2>
This should come up with the position "Quantitative Research Intern" and the company "Point72" and the status should be 1 because it's an application. You'll notice that the email contains the company name in the subject and the position in the body. Notice how the company name may be in places other than the body, and how sometimes you'll have a company like "cubistsystematic" that has nothing to do with the application but is simply the provider for the team's talent acquisition team and nothing else - you can ignore that.
</Analysis 2>

<Example 3>
Subject: Success! We've received your application
From: "HERE @ icims" <here+autoreply@talent.icims.com>
Body: Hi Islam,

Great news! We've received your application for the Software Engineer Intern 2025-75486
position. We could not be more excited that you are considering HERE Technologies as your destination and sincerely respect the time it took you to apply.

Although this is an automated response, we will carefully review your resume and qualifications as they relate to the role(s) you applied for. While sometimes we can find ourselves buried in resumes, you will receive an update from a real person within a week. After all, we've all been in the position of waiting to hear back from someone.

As we begin to learn more about you and your story, please don't hesitate to dive deeper into ours! HERE360 will keep you up to date, our YouTube channel shows you what we're all about, and our Careers site highlights our culture of innovation and commitment to inclusion and diversity.

Thank you very much for your interest in joining our team at HERE Technologies.


The HERE Talent Acquisition Team
Make HERE your destination, we are just getting started.

This message was sent to islam.moh.islamm@gmail.com. If you don't want to receive these emails from this company in the future, please go to:
https://here.icims.com/icims2/?r=4F8F486628&contactId=2786387&pid=17

© HERE International B.V.; PO Box 1300; Eindhoven, (Netherlands) 5602 BH; NLD

CONFIDENTIALITY NOTICE This e-mail and any attachments hereto may contain information that is privileged or confidential, and is intended for use only by the individual or entity to which it is addressed. Any disclosure, copying or distribution of the information by anyone else is strictly prohibited. If you have received this document in error, please notify us promptly by responding to this e-mail. Thank you.
</Example 3>
<Analysis 3>
This is fairly standard. The position is "Software Engineer Intern 2025-75486" and the company is "HERE Technologies". The status is 1 because it's an application.
</Analysis 3>

<Example 4>
asco@myworkday.com
Verify your candidate account
ASCO_header_email.png
Click this link to confirm your email address and complete setup for your candidate account
https://asco.wd5.myworkdayjobs.com/ASCO/activate/gszywz3n2w34ylmws5xqjlwsr2c2xkiwukmo2fhicllln7bjiv9sh2r1q0o81zinr6ynfb54a7jxl2gqd3fbagl22h1scad3sd/?redirect=%2Fen-US%2FASCO%2Fjob%2FAlexandria%252C-VA%2FData-Engineer-Intern_R964-1%2Fapply%2FautofillWithResume
The link will expire after 24 hours.
</Example 4>
<Analysis 4>
This should be totally ignored. It's a verification email for a candidate account and not an application. The position is "UNKNOWN" and the company is "UNKNOWN" and the status is 1 because it's not an application.
</Analysis 4>

<Example 5>
no-reply-recruiting@sofi.org
Islam, an update on your SoFi Intern, Credit Risk Analytics application
Hi Islam,

Thank you for applying for the Intern, Credit Risk Analytics position at SoFi! We're changing the way people think about and interact with personal finance, and we are grateful for your interest in being a part of this journey.

At this time, we have decided to move forward with other candidates whose skill set and experience more closely align with what we're looking for in this role. We wish you the best of luck in your job search!

All the best,

The SoFi Recruiting Team

**Please note: Do not reply to this email. This email is sent from an unattended mailbox and replies will not be read.
</Example 5>
<Analysis 5>
This is a rejection email. The position is "Intern, Credit Risk Analytics" and the company is "SoFi". The status is 0 because it's a rejection.
</Analysis 5>

<Example 6>
Thank you for your application for Summer 2025 Data Engineer Intern – ORBIT 2506236580W

Thank you for applying for Summer 2025 Data Engineer Intern – ORBIT (2506236580W) at Janssen Research & Development, LLC.  We have successfully received your application.  We appreciate your interest in joining us.  When you join Johnson & Johnson, your next move could mean our next breakthrough.

Best Regards,
THE JOHNSON & JOHNSON TALENT ACQUISITION TEAM

Log in to Shine and access real-time updates and resources to keep you informed and prepared for each step along the way.
Visit jobs.jnj.com
   © 2019 Johnson & Johnson Services, Inc.

Please note: Privacy Policy & Legal Notice
Please do not reply to this message. Replies are undeliverable and will not reach the Human Resources Department.
Confidentiality Notice: This e-mail transmission may contain confidential or legally privileged information that is intended only for the individual or entity named in the e-mail address. If you are not the intended recipient, you are hereby notified that any disclosure, copying, distribution, or reliance upon the contents of this e-mail is strictly prohibited. If you have received this e-mail transmission in error, please delete the message from your Inbox. Thank you.

</Example 6>
<Analysis 6>
This is an application. The position is "Summer 2025 Data Engineer Intern – ORBIT (2506236580W)" and the company is "Johnson & Johnson [Janssen Research & Development, LLC]". The status is 1 because it's an application. Notice the subsidiary in square brackets since the parent company is Johnson & Johnson, which can be inferred b.
</Analysis 6>

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
            "subject": subject,
            "full_content": email_content,
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
            "full_content": "",
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

    # Display full email content to help user determine missing information
    if "full_content" in email_data and email_data["full_content"]:
        print("\n--- EMAIL CONTENT ---")
        print(email_data["full_content"])
        print("--- END EMAIL CONTENT ---\n")

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
            email_data = get_email_content(gmail_service, msg["id"])
            print(f"Processing email {i + 1}/{len(messages)}: {email_data['subject']}")

            if (
                email_data["position"] == "UNKNOWN"
                and email_data["company"] == "UNKNOWN"
            ):
                print("⚠️ Unable to extract info from email")
                print()  # Add line break after each email
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
                    print()  # Add line break after each email
                    continue

            entry_key = f"{email_data['position']}_{email_data['company']}"
            if entry_key in existing_entries:
                print(
                    f"ℹ️ Skipping duplicate: {email_data['position']} at {email_data['company']}"
                )
                print()  # Add line break after each email
                continue

            existing_entries.add(entry_key)
            append_to_sheets(sheets_service, spreadsheet_id, email_data)

            status_map = {0: "Rejected", 1: "Applied", 2: "Assessment", 3: "Interview"}
            status_text = status_map.get(email_data["status"], "Unknown")

            print(
                f"✓ Added: {email_data['position']} at {email_data['company']} - Status: {email_data['status']} ({status_text})"
            )
            print()  # Add line break after each email

        except Exception as e:
            logger.error(f"Error processing email {i + 1}: {str(e)}")
            print()  # Add line break even after error

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
