# Job Sheet Tracker
A command-line interface (CLI) tool designed to automatically update a Google Sheet with details from the latest job applications received via Gmail.  This simplifies the process of tracking applications, eliminating manual data entry.

## Features
* **Gmail Integration:** Connects to your Gmail account to retrieve the latest emails.
* **Email Parsing:** Extracts key information from emails, including subject, sender, date, and email body (truncated to 50,000 characters).
* **Google Sheets Integration:** Appends extracted email data to a specified Google Sheet.
* **CLI Usage:**  A simple and user-friendly command-line interface for easy interaction.
* **Configuration via Environment Variables:**  Uses environment variables to store sensitive information like Google Sheet ID and avoids hardcoding credentials directly in the script.

## TODO #022225
- [ ] Integrate with Yihong's internship application tracker.
- [ ] Implement self-updating functionality for roles (automatically update status if the same role and company are detected).
- [ ] Improve email filtering to accurately identify job applications among other emails (so you can parse them daily later on and fully automate the process).
- [ ] Make it an actual global CLI.

## Usage
1. **Set up Environment Variables:** Create a `.env` file in the root directory and set the following environment variables:
    * `GOOGLE_SHEETS_ID`: Your Google Sheet's ID.  You can find this in the URL of your Google Sheet.
    * `GOOGLE_APPLICATION_CREDENTIALS`: Path to your credentials.json file (downloaded from Google Cloud Platform).

2. **Run the script:** Execute the script using the following command, replacing `<number>` with the desired number of latest emails to process:

```bash
python code/script.py --number <number>
```

For example, to process the 10 latest emails:

```bash
python code/script.py --number 10
```

## Installation
1. **Clone the repository:**
```bash
git clone https://github.com/IslamTayeb/job-sheet-tracker.git
```

2. **Set up Google Cloud Credentials:**
    * Create a new project in the Google Cloud Console.
    * Enable the Gmail API and Google Sheets API.
    * Create OAuth 2.0 client ID credentials (downloaded as `credentials.json`).
    * Place `credentials.json` in the root directory of this project

## Technologies Used
* **Python:** The primary programming language for the script.
* **Google API Client Library for Python:** Used for interacting with the Gmail and Google Sheets APIs.
* **google-auth-oauthlib:**  Handles authentication with Google services.
* **google-auth-httplib2:** Provides HTTP client for Google APIs
* **googleapiclient:**  A client library for accessing Google APIs.
* **argparse:** For parsing command-line arguments.
* **dotenv:**  For loading environment variables from a `.env` file.
* **pickle:** For securely storing authentication tokens locally.


## Contributing
Contributions are welcome! Please open an issue or submit a pull request.

*README.md was made with [Etchr](https://etchr.dev)*