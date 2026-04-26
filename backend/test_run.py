import asyncio
from pydantic import BaseModel
import json

from agents.researcher import ResearcherAgent
from agents.generator import GeneratorAgent
from agents.evaluator import EvaluatorAgent
from agents.tech_eval import TechEvaluatorAgent

def test():
    researcher = ResearcherAgent()
    generator = GeneratorAgent()
    evaluator = EvaluatorAgent()
    tech_evaluator = TechEvaluatorAgent()
    
    company = "SK Hynix"
    target_year = 2024
    validation_year = 2023
    
    print(f"Testing pipeline for {company}")
    
    # 1. Research
    print("Running research...")
    research_result = researcher.research_company(company, target_year)
    print("Research Done")
    
    # 2. Generator
    print("Running generator...")
    initial_model = generator.generate_financial_model(company, target_year, research_result['synthesized_facts'])
    print("Generation Done")
    
    # 3. Evaluator
    print("Running evaluator...")
    evaluation_result = evaluator.calculate_loss_and_feedback(company, validation_year, initial_model, 32700000000000)
    print("Evaluation Done", evaluation_result)
    
    # 4. Tech Eval
    print("Running Tech Evaluator...")
    final_payload = tech_evaluator.package_final_report(company, target_year, research_result['synthesized_facts'], initial_model, str(evaluation_result))
    
    print("FINAL OUTPUT:")
    print(json.dumps(final_payload, indent=2))
    
if __name__ == "__main__":
    test()
