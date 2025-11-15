"""LLM client abstraction for Google Gemini."""
import json
import os
import time
import re
from typing import Protocol, Optional, List
from collections import deque
from config import (
    GEMINI_API_KEY, 
    GEMINI_MODEL_NAME,
    GEMINI_RATE_LIMIT_REQUESTS_PER_MINUTE,
    GEMINI_RATE_LIMIT_WINDOW_SECONDS,
    GEMINI_RETRY_DELAY_SECONDS,
    GEMINI_MAX_RETRIES,
)
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Rate limiter: track request timestamps per model
_gemini_request_timestamps: dict[str, deque] = {}

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None


def list_available_models(api_key: Optional[str] = None) -> List[str]:
    """
    List all available Gemini models for the given API key.
    
    Args:
        api_key: Gemini API key (defaults to GEMINI_API_KEY from config)
        
    Returns:
        List of available model names
    """
    if not GEMINI_AVAILABLE:
        raise ImportError("google-generativeai not installed")
    
    key = api_key or GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    
    try:
        genai.configure(api_key=key)
        models = genai.list_models()
        available_models = []
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                # Extract model name (e.g., "models/gemini-1.5-pro" -> "gemini-1.5-pro")
                model_name = model.name.replace('models/', '')
                available_models.append(model_name)
        return available_models
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        raise RuntimeError(f"Failed to list available models: {str(e)}")


class LLMClient(Protocol):
    """Protocol for LLM clients."""
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat message to the LLM.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User message
            
        Returns:
            Assistant's response text
        """
        ...


def _check_gemini_rate_limit(model_name: str) -> None:
    """
    Check if we're within Gemini API rate limit, wait if necessary.
    
    Free tier: 10 requests per minute per model
    """
    if model_name not in _gemini_request_timestamps:
        _gemini_request_timestamps[model_name] = deque()
    
    timestamps = _gemini_request_timestamps[model_name]
    current_time = time.time()
    
    # Remove timestamps outside the time window
    while timestamps and current_time - timestamps[0] > GEMINI_RATE_LIMIT_WINDOW_SECONDS:
        timestamps.popleft()
    
    # If we're at the limit, wait until the oldest request expires
    if len(timestamps) >= GEMINI_RATE_LIMIT_REQUESTS_PER_MINUTE:
        oldest_timestamp = timestamps[0]
        wait_time = GEMINI_RATE_LIMIT_WINDOW_SECONDS - (current_time - oldest_timestamp) + 0.5
        if wait_time > 0:
            logger.warning(f"Gemini rate limit reached for {model_name}. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            # Clean up again after waiting
            current_time = time.time()
            while timestamps and current_time - timestamps[0] > GEMINI_RATE_LIMIT_WINDOW_SECONDS:
                timestamps.popleft()
    
    # Record this request
    timestamps.append(time.time())


def _extract_retry_delay(error_msg: str) -> float:
    """
    Extract retry delay from Gemini API error message.
    
    Returns:
        Retry delay in seconds, or default delay if not found
    """
    # Look for "Please retry in X.XXXXs" pattern
    match = re.search(r'Please retry in ([\d.]+)s', error_msg)
    if match:
        try:
            return float(match.group(1)) + 0.5  # Add small buffer
        except ValueError:
            pass
    
    # Look for retry_delay { seconds: X } pattern
    match = re.search(r'seconds:\s*(\d+)', error_msg)
    if match:
        try:
            return float(match.group(1)) + 0.5
        except ValueError:
            pass
    
    return GEMINI_RETRY_DELAY_SECONDS


def get_gemini_rate_limit_status(model_name: str) -> dict:
    """
    Get current Gemini API rate limit status for a model.
    
    Args:
        model_name: Model name to check
        
    Returns:
        Dictionary with rate limit information
    """
    if model_name not in _gemini_request_timestamps:
        _gemini_request_timestamps[model_name] = deque()
    
    timestamps = _gemini_request_timestamps[model_name]
    current_time = time.time()
    
    # Clean up old timestamps
    while timestamps and current_time - timestamps[0] > GEMINI_RATE_LIMIT_WINDOW_SECONDS:
        timestamps.popleft()
    
    requests_in_window = len(timestamps)
    remaining_requests = max(0, GEMINI_RATE_LIMIT_REQUESTS_PER_MINUTE - requests_in_window)
    
    return {
        "model": model_name,
        "requests_in_window": requests_in_window,
        "remaining_requests": remaining_requests,
        "rate_limit": GEMINI_RATE_LIMIT_REQUESTS_PER_MINUTE,
        "window_seconds": GEMINI_RATE_LIMIT_WINDOW_SECONDS,
    }


class GeminiClient:
    """Google Gemini LLM client implementation."""
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize Gemini client.
        
        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY from config)
            model_name: Model name (defaults to GEMINI_MODEL_NAME from config)
            
        Raises:
            ValueError: If API key is not set
            ImportError: If google-generativeai is not installed
            RuntimeError: If model is not found or not available
        """
        self.api_key = api_key or GEMINI_API_KEY
        self.model_name = model_name or GEMINI_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set. Please set it in environment or .env file.")
        
        if not GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai not installed. "
                "Install with: pip install google-generativeai"
            )
        
        genai.configure(api_key=self.api_key)
        
        # Try to initialize the model, with helpful error messages
        try:
            self.model = genai.GenerativeModel(self.model_name)
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                # Try to list available models and suggest alternatives
                try:
                    available = list_available_models(self.api_key)
                    suggestion = f"\n\nAvailable models: {', '.join(available[:5])}"
                    if len(available) > 5:
                        suggestion += f" (and {len(available) - 5} more)"
                    suggestion += "\nTry updating GEMINI_MODEL_NAME in config.py or .env file."
                except Exception:
                    suggestion = "\n\nTry using 'gemini-1.5-pro' or 'gemini-1.5-flash' instead."
                
                raise RuntimeError(
                    f"Model '{self.model_name}' not found or not available. {error_msg}{suggestion}"
                )
            else:
                raise RuntimeError(f"Failed to initialize Gemini model: {error_msg}")
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat message to Gemini with rate limiting and retry logic.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User message
            
        Returns:
            Assistant's response text
            
        Raises:
            RuntimeError: If API call fails after retries
        """
        # Combine system and user prompts
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Check rate limit before making request
        _check_gemini_rate_limit(self.model_name)
        
        last_error = None
        for attempt in range(GEMINI_MAX_RETRIES):
            try:
                response = self.model.generate_content(full_prompt)
                return response.text
            except Exception as e:
                error_msg = str(e)
                last_error = e
                
                # Check if it's a rate limit error (429)
                if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                    if attempt < GEMINI_MAX_RETRIES - 1:
                        # Extract retry delay from error message
                        retry_delay = _extract_retry_delay(error_msg)
                        logger.warning(
                            f"Gemini API rate limit hit (attempt {attempt + 1}/{GEMINI_MAX_RETRIES}). "
                            f"Retrying in {retry_delay:.1f} seconds..."
                        )
                        time.sleep(retry_delay)
                        # Update rate limiter after waiting
                        _check_gemini_rate_limit(self.model_name)
                        continue
                    else:
                        raise RuntimeError(
                            f"Gemini API rate limit exceeded after {GEMINI_MAX_RETRIES} attempts. "
                            f"Free tier limit: {GEMINI_RATE_LIMIT_REQUESTS_PER_MINUTE} requests/minute. "
                            f"Please wait a minute or upgrade your API plan. Error: {error_msg}"
                        )
                else:
                    # Not a rate limit error, don't retry
                    raise RuntimeError(f"Gemini API error: {error_msg}")
        
        # Should not reach here, but just in case
        raise RuntimeError(f"Gemini API error after {GEMINI_MAX_RETRIES} attempts: {str(last_error)}")
    
    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        """
        Send a chat message and parse JSON response.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User message
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            ValueError: If response is not valid JSON
        """
        response_text = self.chat(system_prompt, user_prompt)
        
        # Try to extract JSON from markdown code blocks
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {str(e)}\nResponse: {response_text}")

