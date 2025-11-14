"""Configuration constants for the SCTP Job Recommender application."""
import os
from dotenv import load_dotenv

load_dotenv()

# LLM Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-pro")

# FindSGJobs API Configuration
FIND_SGJOBS_BASE_URL = "https://www.findsgjobs.com/apis/job/searchable"
FIND_SGJOBS_TIMEOUT = 10
FIND_SGJOBS_MAX_PAGES = 5

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

