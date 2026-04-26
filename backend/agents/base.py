import json
from typing import Any, Optional

from google import genai


class BaseAgent:
    def __init__(self, role: str, client: Optional[genai.Client], model_id: str):
        self.role = role
        self.client = client
        self.model_id = model_id

    def prompt_model(self, prompt: str) -> str:
        if self.client is None:
            return ""
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
            )
            return response.text or ""
        except Exception as exc:
            print(f"[{self.role}] Gemini call failed: {exc}")
            return ""

    def prompt_model_for_json(
        self,
        prompt: str,
        model_override: Optional[str] = None,
    ) -> Any:
        """
        Calls Gemini with JSON output mode and parses the response.
        Returns ``None`` on failure so callers can fall back deterministically.
        """
        if self.client is None:
            return None

        model_to_use = model_override or self.model_id
        try:
            response = self.client.models.generate_content(
                model=model_to_use,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            raw = response.text or ""
        except Exception as exc:
            print(f"[{self.role}] JSON Gemini call failed: {exc}")
            return None

        if not raw:
            return None

        # Strip markdown fences if Gemini returned them despite JSON mime.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].lstrip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            print(f"[{self.role}] JSON parse failure: {exc}; raw={cleaned[:200]}...")
            return None
