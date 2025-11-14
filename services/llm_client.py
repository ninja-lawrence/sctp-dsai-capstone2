"""LLM client abstraction for Google Gemini."""
import json
import os
from typing import Protocol, Optional
from config import GEMINI_API_KEY, GEMINI_MODEL_NAME

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None


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


class GeminiClient:
    """Google Gemini LLM client implementation."""
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize Gemini client.
        
        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY from config)
            model_name: Model name (defaults to GEMINI_MODEL_NAME from config)
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
        self.model = genai.GenerativeModel(self.model_name)
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat message to Gemini.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User message
            
        Returns:
            Assistant's response text
        """
        # Combine system and user prompts
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            response = self.model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {str(e)}")
    
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

