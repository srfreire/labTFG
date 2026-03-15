"""Shared test configuration — loads .env for integration tests."""
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (phase2-juan/)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
