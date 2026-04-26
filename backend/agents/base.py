import os
from google import genai

class BaseAgent:
    def __init__(self, role: str, client: genai.Client, model_id: str):
        self.role = role
        self.client = client
        self.model_id = model_id

    def prompt_model(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            return f"Error communicating with Gemini API: {str(e)}"
