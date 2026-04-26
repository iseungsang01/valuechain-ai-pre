import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

class BaseAgent:
    def __init__(self, role: str):
        self.role = role
        # Initialize Gemini 3.1 Pro Client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_id = "gemini-3.1-pro-preview"

    def prompt_model(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            return f"Error communicating with Gemini API: {str(e)}"
