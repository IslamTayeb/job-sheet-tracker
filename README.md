# Job Sheet Tracker
A command-line interface (CLI) tool designed to automatically update a Google Sheet with details from the latest job applications received via Gmail. This simplifies the process of tracking applications, eliminating manual data entry.

<div align="center">
<img src="https://github.com/IslamTayeb/job-sheet-tracker/blob/main/jobtrack/public/image-1740688549700.png?raw=true" alt="image-1740688549700.png" />
</div>

<video src="https://github.com/IslamTayeb/job-sheet-tracker/blob/main/jobtrack/public/Demo-Video.mp4" />


## Features
* **Gmail Integration:** Connects to your Gmail account to retrieve the latest emails.
* **AI-powered Parsing:** Uses Google's Gemini AI to extract job information like position, company, and application status.
* **Google Sheets Integration:** Appends extracted job data to a specified Google Sheet.
* **CLI Interface:** Simple command-line interface with configuration options.
* **Global Installation:** Can be installed as a global pip package for easy access.

## Installation
### Option 1: Install from GitHub

```bash
pip install git+https://github.com/IslamTayeb/job-sheet-tracker.git
```

### Option 2: Manual Installation

```bash
git clone https://github.com/IslamTayeb/job-sheet-tracker.git
cd job-sheet-tracker
pip install -e .
```

After installation, the `track` command will be available globally in your terminal.  If you use pyenv or another Python version manager, you might need to alias it from a custom environment:

```bash
# After installing it into a virtual environment:
echo 'alias track="~/.pyenv/versions/INSERT-VENV-NAME/bin/track"' >> ~/.zshrc
source ~/.zshrc
```

## Configuration
Before using the tool, you must configure it with your Gemini API key, Google Sheets ID, and Google API credentials:

1. **Get a Gemini API key:**
   - Visit [Google AI Studio](https://makersuite.google.com/app/apikey) to create a Gemini API key.

2. **Create a Google API Credentials file:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project.
   - Enable the Gmail API and Google Sheets API.
   - Create OAuth 2.0 client ID credentials (download as `credentials.json`).

3. **Set up a Google Sheet to store your job applications:**
   - Create a new Google Sheet.
   - Note the Sheet ID from its URL (the long string between `/d/` and `/edit` in the URL).
   - Ensure the sheet has headers in row 1:  `Date`, `Position`, `Company`, `Status`.

4. **Configure the tool:**  Use the following commands, replacing placeholders with your actual values:

```bash
# Set your Gemini API key
track config --gemini-api-key YOUR_API_KEY

# Set your Google Sheets ID
track config --sheets-id YOUR_SHEET_ID

# Set your Google API credentials (choose one method)
track config --credentials path/to/your/credentials.json
# OR
track config --credentials-input  # Paste credentials interactively
```

## Usage
### Process emails to find job applications

```bash
# Process the 10 latest emails
track process 10
```

For backward compatibility:

```bash
track 10
```

### View or update configuration

```bash
# View current configuration
track config

# Update Gemini API key
track config --gemini-api-key YOUR_NEW_API_KEY

# Update Google Sheets ID
track config --sheets-id YOUR_NEW_SHEET_ID
```

## Google Sheet Format
The tool expects a Google Sheet with the following columns:

1. **Date:** When the application was submitted/processed.
2. **Position:** Job title or position.
3. **Company:** Company name.
4. **Status:** Application status (0=Rejected, 1=Applied, 2=Assessment, 3=Interview).

## Job Status Codes
- **0**: Rejected
- **1**: Applied
- **2**: Assessment/Screening
- **3**: Interview

## Technologies Used
* **Python:** The primary programming language for the application logic.
* **Google Gmail API:** Used to access and retrieve emails from a Gmail account.
* **Google Sheets API:** Used to interact with and update data in a Google Sheet.
* **Google Gemini API:**  Leverages Gemini's AI capabilities for natural language processing to extract relevant information from emails.
* **google-api-python-client:** Python client library for Google APIs.
* **google-auth-httplib2:** Authentication library for Google APIs.
* **google-auth-oauthlib:** OAuth 2.0 client library for Google APIs.
* **google-generativeai:** Python client library for Google Generative AI models.
* **python-dotenv:**  Loads environment variables from a `.env` file.
* **pytz:** World timezone definitions.
* **setuptools:** Used for packaging and distributing the Python project.

## Dependencies
The project's dependencies are listed in `requirements.txt`.  You can install them using:

```bash
pip install -r requirements.txt
```

## Contributing
Contributions are welcome! Please open an issue or submit a pull request.

*README.md was made with [Etchr](https://etchr.dev)*