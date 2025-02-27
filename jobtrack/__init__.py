"""
JobTrack - A CLI tool to track job applications in Google Sheets using Gmail and Gemini AI.
"""

__version__ = "0.2.0"

from .tracker import main_cli

__all__ = ['main_cli']
