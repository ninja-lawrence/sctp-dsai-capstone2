"""Configuration constants for the SCTP Job Recommender application."""
import os
from dotenv import load_dotenv

load_dotenv()

# LLM Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Default to gemini-1.5-flash (faster and more widely available)
# Alternatives: gemini-1.5-pro, gemini-pro
# If this doesn't work, use list_available_models() in llm_client.py to see available models
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

# Gemini API Rate Limiting
# Free tier: 10 requests per minute per model
# Paid tier: Higher limits
GEMINI_RATE_LIMIT_REQUESTS_PER_MINUTE = 10  # Conservative limit for free tier
GEMINI_RATE_LIMIT_WINDOW_SECONDS = 60
GEMINI_RETRY_DELAY_SECONDS = 2  # Initial retry delay
GEMINI_MAX_RETRIES = 3

# FindSGJobs API Configuration
FIND_SGJOBS_BASE_URL = "https://www.findsgjobs.com/apis/job/searchable"
FIND_SGJOBS_TIMEOUT = 10
FIND_SGJOBS_MAX_PAGES = 5
FIND_SGJOBS_RATE_LIMIT = 60  # Requests per minute (per IP)
FIND_SGJOBS_RATE_LIMIT_WINDOW = 60  # Time window in seconds

# Application Configuration
APP_TITLE = "SCTP Job Recommender & Skill Gap Analyzer"
DEFAULT_KEYWORDS = "data analyst"
TOP_K_JOBS = 10

# Employment Types Mapping
EMPLOYMENT_TYPES = {
    "full_time": 76,
    "part_time": 977,
    "permanent": 978,
    "temporary": 979,
    "contract": 980,
    "internship": 981,
    "freelance": 982,
    "contract_to_perm": 983,
}

# Currency IDs
CURRENCIES = {
    "SGD": 1275916990,
    "MYR": 1275916991,
    "USD": 1275916992,
    "IND": 1275916993,
}

# Salary Intervals
SALARY_INTERVALS = {
    "hour": 1895,
    "day": 1896,
    "week": 1897,
    "month": 1898,
    "annual": 1899,
}

