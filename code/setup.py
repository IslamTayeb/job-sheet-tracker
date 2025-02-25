from setuptools import setup, find_packages

setup(
    name="jobtrack",
    version="0.2.0",
    packages=find_packages(),
    install_requires=[
        "google-api-python-client",
        "google-auth-httplib2",
        "google-auth-oauthlib",
        "google-generativeai",
        "python-dotenv",
        "pytz",
    ],
    entry_points={
        "console_scripts": [
            "track=jobtrack.tracker:main_cli",
        ],
    },
    author="Islam Tayeb",
    description="A CLI tool to track job applications in Google Sheets using Gmail and Gemini AI",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/IslamTayeb/job-sheet-tracker",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.7",
)
