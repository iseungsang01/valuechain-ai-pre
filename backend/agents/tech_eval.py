from .base import BaseAgent

class TechEvaluatorAgent(BaseAgent):
    def __init__(self):
        super().__init__(role="TechEvaluator")

    def package_final_report(self, company_name: str, target_year: int, research_facts: str, final_model: str, evaluation_feedback: str = None) -> dict:
        """
        Validates citations and formats the output specifically for the octo-code-DESIGN frontend.
        Returns a dict containing terminal logs and structured data.
        """
        # In a real 24h hackathon, we can use Gemini to structure it perfectly, 
        # but to save time & ensure stability, we will just format it programmatically or via a light prompt.
        
        prompt = f"""
        You are the Tech Overall Evaluator.
        Your job is to take the raw outputs of the research and financial modeling process and format them 
        into a clean, developer-friendly JSON structure that will be rendered on an "octo-code-DESIGN" frontend.
        
        Company: {company_name}
        Year: {target_year}
        
        Research Facts: {research_facts}
        Final Model: {final_model}
        Feedback/Evaluation (if any): {evaluation_feedback or "N/A"}
        
        Ensure that ALL numeric claims have a [Source] attached to them (from the Research Facts).
        
        Output MUST be valid JSON with the following schema:
        {{
            "company": "{company_name}",
            "year": {target_year},
            "executive_summary": "<string>",
            "terminal_logs": [
                "[Researcher] Fetched data...",
                "[Generator] Calculating PxQ...",
                ...
            ],
            "financial_data": {{
                "estimated_revenue_krw": "<string>",
                "estimated_op_krw": "<string>",
                "key_drivers": ["<string>"]
            }},
            "citations": [
                {{"id": 1, "text": "<string>", "url": "<string>"}}
            ]
        }}
        """
        
        raw_response = self.prompt_model(prompt)
        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:-3]
        elif cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:-3]
            
        try:
            import json
            return json.loads(cleaned_response)
        except:
            # Fallback mock format
            return {
                "company": company_name,
                "year": target_year,
                "executive_summary": "Failed to parse final JSON, falling back to raw text.",
                "raw_text": raw_response,
                "terminal_logs": ["[Error] JSON parse failed in Tech Evaluator"]
            }
