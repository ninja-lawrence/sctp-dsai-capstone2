"""Configuration constants for the SCTP Job Recommender application."""
import os
from dotenv import load_dotenv

load_dotenv()

# LLM Configuration - Ollama
# Default Ollama base URL (local server)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Default model: deepseek-r1 (DeepSeek R1 model)
# Alternatives: llama3, mistral, deepseek-coder, etc.
# To see available models: ollama list
# To see available models, use list_available_models() in llm_client.py
# To pull a model, run: ollama pull <model_name>
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "deepseek-r1")

# Ollama Rate Limiting
# Rate limiting is configurable based on your system capacity
OLLAMA_RATE_LIMIT_REQUESTS_PER_MINUTE = 60  # Adjust based on your system
OLLAMA_RATE_LIMIT_WINDOW_SECONDS = 60
OLLAMA_RETRY_DELAY_SECONDS = 2  # Initial retry delay
OLLAMA_MAX_RETRIES = 3
OLLAMA_TIMEOUT_SECONDS = 300  # Timeout for requests (longer for local inference - increased for slow models)

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

