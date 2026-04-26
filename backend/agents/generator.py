from google import genai
from .base import BaseAgent

class GeneratorAgent(BaseAgent):
    def __init__(self, client: genai.Client, model_id: str):
        super().__init__(role="Generator", client=client, model_id=model_id)

    def generate_financial_model(self, company_name: str, target_year: int, research_facts: str) -> str:
        """
        Creates a PxQ financial model based on the facts provided by the Researcher.
        """
        prompt = f"""
        You are an expert Financial Modeler specializing in the Semiconductor industry.
        Your task is to estimate the revenue and costs for {company_name} for the year {target_year}.
        
        Use the following research facts to build your model:
        {research_facts}
        
        Your output MUST strictly follow this thinking process:
        1. [Classification] Identify if the company is an IDM (like Samsung/SK Hynix) or an Equipment/Material supplier.
        2. [Logic Building] Define the specific P (Price/ASP) and Q (Volume/Shipments) metrics relevant to this company.
        3. [Calculation] Step-by-step estimate the Revenue (P * Q) and operational costs. Use realistic assumptions if exact numbers are missing, but explicitly state your assumptions.
        4. [Final Estimate] Provide the final estimated Revenue and Operating Profit in KRW (Korean Won).
        
        Return the result in clear Markdown format suitable for developer terminal output.
        """
        return self.prompt_model(prompt)
