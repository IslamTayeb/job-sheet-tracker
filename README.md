# Job Sheet Tracker

A command-line interface (CLI) tool designed to automatically update a Google Sheet with details from the latest job applications received via Gmail. This simplifies the process of tracking applications, eliminating manual data entry.

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

After installation, the `track` command will be available globally in your terminal. Sometimes if you use pyenv or other python version manager, you'd require to alias it from a custom environment:

```bash
# After installing it into a venv:
echo 'alias track="~/.pyenv/versions/INSERT-VENV-NAME/bin/track"' >> ~/.zshrc
source ~/.zshrc
```

## Initial Setup

Before using the tool, you need to configure it with your Gemini API key, Google Sheets ID, and Google API credentials:

1. **Get a Gemini API key:**
   - Visit [Google AI Studio](https://makersuite.google.com/app/apikey) to create a Gemini API key.

2. **Create a Google API Credentials file:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the Gmail API and Google Sheets API
   - Create OAuth 2.0 client ID credentials (download as `credentials.json`)

3. **Set up a Google Sheet to store your job applications:**
   - Create a new Google Sheet
   - Note the Sheet ID from its URL (the long string between /d/ and /edit in the URL)
   - Make sure the sheet has headers in row 1

4. **Configure the tool:**

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

For backward compatibility, you can also simply use:

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
1. **Date** - When the application was submitted/processed
2. **Position** - Job title or position
3. **Company** - Company name
4. **Status** - Application status (0=Rejected, 1=Applied, 2=Assessment, 3=Interview)

## Job Status Codes

The tool uses the following status codes in the Google Sheet:
- **0**: Rejected
- **1**: Applied
- **2**: Assessment/Screening
- **3**: Interview

## Troubleshooting

- **Authentication Issues**: If you encounter authentication problems, delete the token files in `~/.jobtrack/` and run the tool again.
- **Missing Information**: If the tool cannot extract job information from emails, it will prompt you to enter it manually.
- **Configuration Errors**: Run `track config` to verify your current configuration.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

MIT
