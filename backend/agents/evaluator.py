import json
from google import genai
from .base import BaseAgent

class EvaluatorAgent(BaseAgent):
    def __init__(self, client: genai.Client, model_id: str):
        super().__init__(role="Evaluator", client=client, model_id=model_id)

    def calculate_loss_and_feedback(self, company_name: str, validation_year: int, estimated_model: str, ground_truth_revenue: float) -> dict:
        """
        Compares the generated estimate against the actual ground truth (simulated for the validation year).
        Returns the Loss score and detailed feedback to improve the Generator's logic.
        """
        prompt = f"""
        You are the Model Evaluator (Tech Lead). 
        A Generator Agent has produced the following financial estimate for {company_name} in {validation_year}:
        
        <estimated_model>
        {estimated_model}
        </estimated_model>
        
        The ACTUAL Ground Truth Revenue for {company_name} in {validation_year} was roughly {ground_truth_revenue} KRW.
        
        1. Parse the estimated revenue from the <estimated_model>. (If multiple, pick the main total revenue).
        2. Calculate the Loss Function using this exact formula:
           Loss = ((Estimated Revenue - Actual Revenue) / Actual Revenue * 100)^2
        3. Identify WHY the estimate was off. Did the Generator miss a specific cost, overestimate Q, or fail to account for ASP drops?
        4. Provide specific, actionable FEEDBACK for the Generator to fix its logic for future estimations.
        
        Return your response strictly in the following JSON format:
        {{
            "estimated_revenue_parsed": <float>,
            "actual_revenue": {ground_truth_revenue},
            "loss_score": <float>,
            "error_percentage": <float>,
            "evaluation_reasoning": "<string>",
            "feedback_for_generator": "<string>"
        }}
        """
        
        raw_response = self.prompt_model(prompt)
        
        # Clean up markdown code blocks if the model wrapped the JSON
        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:-3]
        elif cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:-3]
            
        try:
            return json.loads(cleaned_response)
        except Exception as e:
            return {
                "error": "Failed to parse Evaluator JSON",
                "raw_response": raw_response
            }
