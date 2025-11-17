"""LLM client abstraction for Ollama."""
import json
import os
import time
import re
from typing import Protocol, Optional, List
from collections import deque
import requests
from config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL_NAME,
    OLLAMA_RATE_LIMIT_REQUESTS_PER_MINUTE,
    OLLAMA_RATE_LIMIT_WINDOW_SECONDS,
    OLLAMA_RETRY_DELAY_SECONDS,
    OLLAMA_MAX_RETRIES,
    OLLAMA_TIMEOUT_SECONDS,
)
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Rate limiter: track request timestamps per model
_ollama_request_timestamps: dict[str, deque] = {}


def list_available_models(base_url: Optional[str] = None) -> List[str]:
    """
    List all available Ollama models.
    
    Args:
        base_url: Ollama base URL (defaults to OLLAMA_BASE_URL from config)
        
    Returns:
        List of available model names
    """
    url = (base_url or OLLAMA_BASE_URL).rstrip('/')
    try:
        response = requests.get(f"{url}/api/tags", timeout=OLLAMA_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        available_models = [model["name"] for model in data.get("models", [])]
        return available_models
    except requests.exceptions.RequestException as e:
        logger.error(f"Error listing models: {str(e)}")
        raise RuntimeError(f"Failed to list available models. Make sure Ollama is running at {url}. Error: {str(e)}")
    except Exception as e:
        logger.error(f"Error parsing model list: {str(e)}")
        raise RuntimeError(f"Failed to parse available models: {str(e)}")


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


def _check_ollama_rate_limit(model_name: str) -> None:
    """
    Check if we're within Ollama rate limit, wait if necessary.
    """
    if model_name not in _ollama_request_timestamps:
        _ollama_request_timestamps[model_name] = deque()
    
    timestamps = _ollama_request_timestamps[model_name]
    current_time = time.time()
    
    # Remove timestamps outside the time window
    while timestamps and current_time - timestamps[0] > OLLAMA_RATE_LIMIT_WINDOW_SECONDS:
        timestamps.popleft()
    
    # If we're at the limit, wait until the oldest request expires
    if len(timestamps) >= OLLAMA_RATE_LIMIT_REQUESTS_PER_MINUTE:
        oldest_timestamp = timestamps[0]
        wait_time = OLLAMA_RATE_LIMIT_WINDOW_SECONDS - (current_time - oldest_timestamp) + 0.5
        if wait_time > 0:
            logger.warning(f"Ollama rate limit reached for {model_name}. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            # Clean up again after waiting
            current_time = time.time()
            while timestamps and current_time - timestamps[0] > OLLAMA_RATE_LIMIT_WINDOW_SECONDS:
                timestamps.popleft()
    
    # Record this request
    timestamps.append(time.time())


def _extract_retry_delay(error_msg: str) -> float:
    """
    Extract retry delay from error message.
    
    Returns:
        Retry delay in seconds, or default delay if not found
    """
    return OLLAMA_RETRY_DELAY_SECONDS


def get_ollama_rate_limit_status(model_name: str) -> dict:
    """
    Get current Ollama rate limit status for a model.
    
    Args:
        model_name: Model name to check
        
    Returns:
        Dictionary with rate limit information
    """
    if model_name not in _ollama_request_timestamps:
        _ollama_request_timestamps[model_name] = deque()
    
    timestamps = _ollama_request_timestamps[model_name]
    current_time = time.time()
    
    # Clean up old timestamps
    while timestamps and current_time - timestamps[0] > OLLAMA_RATE_LIMIT_WINDOW_SECONDS:
        timestamps.popleft()
    
    requests_in_window = len(timestamps)
    remaining_requests = max(0, OLLAMA_RATE_LIMIT_REQUESTS_PER_MINUTE - requests_in_window)
    
    return {
        "model": model_name,
        "requests_in_window": requests_in_window,
        "remaining_requests": remaining_requests,
        "rate_limit": OLLAMA_RATE_LIMIT_REQUESTS_PER_MINUTE,
        "window_seconds": OLLAMA_RATE_LIMIT_WINDOW_SECONDS,
    }


class OllamaClient:
    """Ollama LLM client implementation."""
    
    def __init__(self, base_url: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Ollama base URL (defaults to OLLAMA_BASE_URL from config)
            model_name: Model name (defaults to OLLAMA_MODEL_NAME from config)
            
        Raises:
            ValueError: If base URL is not set
            RuntimeError: If Ollama server is not reachable or model is not available
        """
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip('/')
        self.model_name = model_name or OLLAMA_MODEL_NAME
        
        if not self.base_url:
            raise ValueError("OLLAMA_BASE_URL not set. Please set it in environment or .env file.")
        
        # Verify Ollama server is reachable
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=OLLAMA_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                f"Ollama server not reachable at {self.base_url}. "
                f"Make sure Ollama is running. Error: {str(e)}"
            )
        
        # Verify model is available (optional check - don't fail if listing fails)
        try:
            available_models = list_available_models(self.base_url)
            if self.model_name not in available_models:
                suggestion = f"\n\nAvailable models: {', '.join(available_models[:5])}"
                if len(available_models) > 5:
                    suggestion += f" (and {len(available_models) - 5} more)"
                suggestion += f"\nTry updating OLLAMA_MODEL_NAME in config.py or .env file."
                suggestion += f"\nTo pull a model, run: ollama pull {self.model_name}"
                logger.warning(f"Model '{self.model_name}' not found in available models. {suggestion}")
                # Don't raise error here - let it fail on first use if model really doesn't exist
        except Exception as e:
            # If we can't list models, still try to use the model (might be a listing issue)
            logger.warning(f"Could not verify model availability: {str(e)}. Proceeding anyway.")
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat message to Ollama with rate limiting and retry logic.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User message
            
        Returns:
            Assistant's response text
            
        Raises:
            RuntimeError: If API call fails after retries
        """
        # Check rate limit before making request
        _check_ollama_rate_limit(self.model_name)
        
        # Log request details for debugging
        total_prompt_length = len(system_prompt) + len(user_prompt)
        logger.debug(f"Making Ollama request: model={self.model_name}, prompt_length={total_prompt_length} chars, timeout={OLLAMA_TIMEOUT_SECONDS}s")
        
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False
        }
        
        # Explicit headers to ensure proper request format
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        last_error = None
        start_time = time.time()
        for attempt in range(OLLAMA_MAX_RETRIES):
            try:
                attempt_start = time.time()
                response = requests.post(url, json=payload, headers=headers, timeout=OLLAMA_TIMEOUT_SECONDS)
                
                # Check for 404 before raising for status
                if response.status_code == 404:
                    raise RuntimeError(
                        f"Ollama API endpoint not found (404). "
                        f"This usually means Ollama is not running or the API endpoint has changed. "
                        f"URL: {url}. "
                        f"Make sure Ollama is running: `ollama serve`"
                    )
                
                # Check for 405 Method Not Allowed
                if response.status_code == 405:
                    # Try to get more info from response
                    try:
                        error_detail = response.text[:200] if response.text else "No error details"
                    except:
                        error_detail = "Could not read error details"
                    
                    raise RuntimeError(
                        f"Ollama API method not allowed (405). "
                        f"The endpoint '{url}' does not accept POST requests. "
                        f"This might indicate an Ollama version mismatch or API change. "
                        f"Error details: {error_detail}. "
                        f"Please check your Ollama version (`ollama --version`) and ensure it's up to date. "
                        f"Current Ollama base URL: {self.base_url}"
                    )
                
                response.raise_for_status()
                data = response.json()
                
                # Extract the message content
                if "message" in data and "content" in data["message"]:
                    return data["message"]["content"]
                else:
                    raise RuntimeError(f"Unexpected response format: {data}")
                    
            except requests.exceptions.Timeout as e:
                elapsed_time = time.time() - start_time
                last_error = e
                
                # Determine if it's a read timeout (response taking too long) or connect timeout
                timeout_type = "read timeout" if "Read timed out" in str(e) else "timeout"
                
                if attempt < OLLAMA_MAX_RETRIES - 1:
                    retry_delay = OLLAMA_RETRY_DELAY_SECONDS * (attempt + 1)
                    logger.warning(
                        f"Ollama request {timeout_type} (attempt {attempt + 1}/{OLLAMA_MAX_RETRIES}). "
                        f"Model: {self.model_name}, Prompt length: {total_prompt_length} chars, "
                        f"Timeout: {OLLAMA_TIMEOUT_SECONDS}s. Retrying in {retry_delay:.1f} seconds..."
                    )
                    time.sleep(retry_delay)
                    continue
                else:
                    # Provide detailed error message with suggestions
                    error_details = (
                        f"Ollama request {timeout_type} after {OLLAMA_MAX_RETRIES} attempts.\n"
                        f"Model: {self.model_name}\n"
                        f"Prompt length: {total_prompt_length} characters\n"
                        f"Timeout setting: {OLLAMA_TIMEOUT_SECONDS} seconds\n"
                        f"Total elapsed time: {elapsed_time:.1f} seconds\n\n"
                        f"Possible solutions:\n"
                        f"1. Try a faster/smaller model (e.g., 'llama3', 'mistral', or 'deepseek-coder' instead of 'deepseek-r1')\n"
                        f"2. Reduce prompt length (currently {total_prompt_length} chars)\n"
                        f"3. Increase OLLAMA_TIMEOUT_SECONDS in config.py (currently {OLLAMA_TIMEOUT_SECONDS}s)\n"
                        f"4. Check if Ollama is responding: `curl {self.base_url}/api/tags`\n"
                        f"5. Restart Ollama server: Stop and run `ollama serve` again\n"
                        f"6. Check system resources (CPU/RAM) - the model might be too slow for your hardware\n"
                        f"7. Consider using a GPU-accelerated model if available\n\n"
                        f"Original error: {str(e)}"
                    )
                    logger.error(error_details)
                    raise RuntimeError(error_details)
                    
            except requests.exceptions.HTTPError as e:
                # Handle HTTP errors (including 404, 405)
                error_msg = str(e)
                last_error = e
                
                if hasattr(e, 'response') and e.response is not None:
                    status_code = e.response.status_code
                    if status_code == 404:
                        raise RuntimeError(
                            f"Ollama API endpoint not found (404). "
                            f"This usually means Ollama is not running or the API endpoint has changed. "
                            f"URL: {url}. "
                            f"Make sure Ollama is running: `ollama serve`"
                        )
                    elif status_code == 405:
                        # Try to get more info from response
                        try:
                            error_detail = e.response.text[:200] if e.response.text else "No error details"
                        except:
                            error_detail = "Could not read error details"
                        
                        raise RuntimeError(
                            f"Ollama API method not allowed (405). "
                            f"The endpoint '{url}' does not accept POST requests. "
                            f"This might indicate an Ollama version mismatch or API change. "
                            f"Error details: {error_detail}. "
                            f"Please check your Ollama version (`ollama --version`) and ensure it's up to date. "
                            f"Current Ollama base URL: {self.base_url}"
                        )
                
                # For other HTTP errors, retry
                if attempt < OLLAMA_MAX_RETRIES - 1:
                    retry_delay = OLLAMA_RETRY_DELAY_SECONDS * (attempt + 1)
                    logger.warning(
                        f"Ollama HTTP error (attempt {attempt + 1}/{OLLAMA_MAX_RETRIES}): {error_msg}. "
                        f"Retrying in {retry_delay:.1f} seconds..."
                    )
                    time.sleep(retry_delay)
                    continue
                else:
                    raise RuntimeError(f"Ollama HTTP error after {OLLAMA_MAX_RETRIES} attempts: {error_msg}")
                    
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                last_error = e
                
                # Check if it's a connection error
                if "Connection" in error_msg or "refused" in error_msg.lower():
                    raise RuntimeError(
                        f"Ollama server not reachable at {self.base_url}. "
                        f"Make sure Ollama is running. Error: {error_msg}"
                    )
                
                # Check for 404 in error message as fallback
                if "404" in error_msg or "Not Found" in error_msg:
                    raise RuntimeError(
                        f"Ollama API endpoint not found (404). "
                        f"This usually means Ollama is not running or the API endpoint has changed. "
                        f"URL: {url}. "
                        f"Make sure Ollama is running: `ollama serve`"
                    )
                
                # For other errors, retry
                if attempt < OLLAMA_MAX_RETRIES - 1:
                    retry_delay = OLLAMA_RETRY_DELAY_SECONDS * (attempt + 1)
                    logger.warning(
                        f"Ollama API error (attempt {attempt + 1}/{OLLAMA_MAX_RETRIES}): {error_msg}. "
                        f"Retrying in {retry_delay:.1f} seconds..."
                    )
                    time.sleep(retry_delay)
                    continue
                else:
                    raise RuntimeError(f"Ollama API error after {OLLAMA_MAX_RETRIES} attempts: {error_msg}")
        
        # Should not reach here, but just in case
        raise RuntimeError(f"Ollama API error after {OLLAMA_MAX_RETRIES} attempts: {str(last_error)}")
    
    def _repair_json(self, json_str: str) -> str:
        """
        Attempt to repair common JSON issues.
        
        Args:
            json_str: Potentially malformed JSON string
            
        Returns:
            Repaired JSON string (may still be invalid)
        """
        # Remove URLs from suggested_learning_path if they're causing issues
        # This is a heuristic - try to remove URLs in parentheses from learning path strings
        # Pattern: "Step X: text (https://...)" -> "Step X: text"
        json_str = re.sub(r'\(https?://[^\s\)]+\)', '', json_str)
        json_str = re.sub(r'\(http://[^\s\)]+\)', '', json_str)
        
        # Try to fix incomplete JSON by closing brackets/braces
        # Count open vs closed brackets/braces
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')
        
        # If JSON appears incomplete, try to close it
        if open_braces > close_braces:
            # Check if we're in the middle of a string (don't close if we are)
            # Simple heuristic: if last non-whitespace char is not a quote or comma, we might be mid-string
            trimmed = json_str.rstrip()
            if trimmed and trimmed[-1] not in ['"', ',', ']', '}']:
                # We might be mid-string, try to close the string first
                # Find the last unclosed quote
                last_quote = trimmed.rfind('"')
                if last_quote != -1:
                    # Check if quote is escaped
                    if last_quote == 0 or trimmed[last_quote - 1] != '\\':
                        # Unclosed string - close it
                        json_str = trimmed + '"'
            
            # Close remaining braces
            json_str += '}' * (open_braces - close_braces)
        
        if open_brackets > close_brackets:
            json_str += ']' * (open_brackets - close_brackets)
        
        return json_str
    
    def _extract_json_objects(self, text: str) -> list:
        """
        Extract all JSON objects from text, handling various formats.
        
        Args:
            text: Text that may contain JSON objects
            
        Returns:
            List of extracted JSON objects (as dicts)
        """
        objects = []
        
        # Remove markdown formatting and numbered lists
        # Remove patterns like "1. ", "2. ", etc. at start of lines
        text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
        
        # Find all JSON objects using brace matching
        brace_count = 0
        start_idx = -1
        
        for i, char in enumerate(text):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx != -1:
                    # Found a complete JSON object
                    json_str = text[start_idx:i+1]
                    try:
                        obj = json.loads(json_str)
                        objects.append(obj)
                    except json.JSONDecodeError:
                        # Try to repair and parse again
                        try:
                            repaired = self._repair_json(json_str)
                            obj = json.loads(repaired)
                            objects.append(obj)
                        except (json.JSONDecodeError, AttributeError):
                            # Skip invalid JSON objects
                            pass
                    start_idx = -1
        
        return objects
    
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
        
        # Log raw response for debugging
        logger.debug(f"Raw LLM response (first 500 chars): {response_text[:500]}")
        
        # Check if response is empty
        if not response_text or not response_text.strip():
            raise ValueError("LLM returned empty response. The model might not be responding correctly.")
        
        original_response = response_text
        
        # Try to extract JSON from markdown code blocks
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end == -1:
                # No closing backticks, take everything after opening
                response_text = response_text[start:].strip()
            else:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end == -1:
                # No closing backticks, take everything after opening
                response_text = response_text[start:].strip()
            else:
                response_text = response_text[start:end].strip()
        
        # Try to find JSON array first (for supervisor responses)
        if response_text.strip().startswith('['):
            # Try to extract array
            first_bracket = response_text.find('[')
            last_bracket = response_text.rfind(']')
            if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                array_text = response_text[first_bracket:last_bracket + 1]
                try:
                    parsed = json.loads(array_text)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        # If it's an array, return first element if expecting dict, or wrap in dict
                        # Actually, supervisor expects array, so we need a different method
                        # For now, if we get an array with one dict, return the dict
                        if len(parsed) == 1 and isinstance(parsed[0], dict):
                            return parsed[0]
                        # Otherwise, this is an array response - should use chat_json_array
                        # But for backward compatibility, try to handle it
                        raise ValueError("Got JSON array but expected object. Use chat_json_array() for arrays.")
                except json.JSONDecodeError:
                    pass
        
        # Try to find single JSON object boundaries
        if "{" in response_text and "}" in response_text:
            first_brace = response_text.find("{")
            last_brace = response_text.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                response_text = response_text[first_brace:last_brace + 1]
        
        # Try parsing as single JSON object
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, dict):
                return parsed
            elif isinstance(parsed, list):
                # If we got an array but expected dict, try to extract first element
                if len(parsed) > 0 and isinstance(parsed[0], dict):
                    logger.warning("Got JSON array but expected object. Using first element.")
                    return parsed[0]
                raise ValueError(f"Got JSON array but expected object. Array length: {len(parsed)}")
            else:
                raise ValueError(f"Parsed JSON is not a dictionary. Got type: {type(parsed)}")
        except json.JSONDecodeError as e:
            # Check if JSON appears incomplete (truncated)
            open_braces = response_text.count('{')
            close_braces = response_text.count('}')
            open_brackets = response_text.count('[')
            close_brackets = response_text.count(']')
            
            is_incomplete = (open_braces > close_braces) or (open_brackets > close_brackets)
            
            # Try to repair JSON before giving up
            try:
                repaired_text = self._repair_json(response_text)
                parsed = json.loads(repaired_text)
                if isinstance(parsed, dict):
                    if is_incomplete:
                        logger.warning("Successfully parsed JSON after repair (JSON was incomplete/truncated).")
                    else:
                        logger.warning("Successfully parsed JSON after repair (removed URLs from learning path).")
                    return parsed
            except (json.JSONDecodeError, AttributeError):
                pass
            
            # Try extracting multiple JSON objects (for cases where LLM returns multiple objects)
            extracted_objects = self._extract_json_objects(response_text)
            if extracted_objects:
                if len(extracted_objects) == 1:
                    logger.warning("Extracted single JSON object from malformed response.")
                    return extracted_objects[0]
                else:
                    # Multiple objects found - this might be an array response
                    logger.warning(f"Extracted {len(extracted_objects)} JSON objects. Using first one.")
                    return extracted_objects[0]
            
            # Check if JSON is incomplete
            open_braces = response_text.count('{')
            close_braces = response_text.count('}')
            open_brackets = response_text.count('[')
            close_brackets = response_text.count(']')
            is_incomplete = (open_braces > close_braces) or (open_brackets > close_brackets)
            
            # Provide more helpful error message
            incomplete_msg = ""
            if is_incomplete:
                incomplete_msg = f"\nJSON appears incomplete/truncated: {open_braces} open braces vs {close_braces} closed, {open_brackets} open brackets vs {close_brackets} closed."
            
            error_msg = (
                f"Failed to parse JSON response from LLM.\n"
                f"JSON Error: {str(e)}\n"
                f"Attempted to parse (first 500 chars): {response_text[:500]}\n"
                f"Original response length: {len(original_response)} characters{incomplete_msg}\n"
                f"Tip: The LLM response may be incomplete or contain malformed JSON. Check if the model is hitting token limits."
            )
            logger.error(error_msg)
            logger.debug(f"Full original response: {original_response}")
            raise ValueError(error_msg)
    
    def chat_json_array(self, system_prompt: str, user_prompt: str) -> list:
        """
        Send a chat message and parse JSON array response.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User message
            
        Returns:
            Parsed JSON array
            
        Raises:
            ValueError: If response is not valid JSON array
        """
        response_text = self.chat(system_prompt, user_prompt)
        
        # Log raw response for debugging
        logger.debug(f"Raw LLM response (first 500 chars): {response_text[:500]}")
        
        # Check if response is empty
        if not response_text or not response_text.strip():
            raise ValueError("LLM returned empty response. The model might not be responding correctly.")
        
        original_response = response_text
        
        # Try to extract JSON from markdown code blocks
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end == -1:
                response_text = response_text[start:].strip()
            else:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end == -1:
                response_text = response_text[start:].strip()
            else:
                response_text = response_text[start:end].strip()
        
        # Try to find JSON array
        if "[" in response_text and "]" in response_text:
            first_bracket = response_text.find("[")
            last_bracket = response_text.rfind("]")
            if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                array_text = response_text[first_bracket:last_bracket + 1]
                try:
                    parsed = json.loads(array_text)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
        
        # Try extracting multiple JSON objects and wrapping in array
        extracted_objects = self._extract_json_objects(response_text)
        if extracted_objects:
            logger.warning(f"Extracted {len(extracted_objects)} JSON objects and wrapping in array.")
            return extracted_objects
        
        # Last resort: try parsing as single object and wrapping in array
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, dict):
                logger.warning("Got single JSON object but expected array. Wrapping in array.")
                return [parsed]
        except json.JSONDecodeError:
            pass
        
        # If all else fails, raise error
        error_msg = (
            f"Failed to parse JSON array response from LLM.\n"
            f"Attempted to parse (first 500 chars): {response_text[:500]}\n"
            f"Original response length: {len(original_response)} characters"
        )
        logger.error(error_msg)
        logger.debug(f"Full original response: {original_response}")
        raise ValueError(error_msg)


# Alias for backward compatibility (if needed)
GeminiClient = OllamaClient

