from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import asyncio

from agents.researcher import ResearcherAgent
from agents.generator import GeneratorAgent
from agents.evaluator import EvaluatorAgent
from agents.tech_eval import TechEvaluatorAgent

app = FastAPI(title="Octo-Fin API", description="AI Financial Agent for Semiconductor Supply Chain")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    company_name: str
    target_year: int
    validation_year: int = 2023 

# Instantiate agents
researcher = ResearcherAgent()
generator = GeneratorAgent()
evaluator = EvaluatorAgent()
tech_evaluator = TechEvaluatorAgent()

@app.get("/")
def read_root():
    return {"status": "Octo-Fin API is running"}

@app.post("/api/analyze")
async def run_analysis(req: AnalysisRequest):
    try:
        # Step 1: Research
        print(f"[Researcher] Starting research for {req.company_name} in {req.target_year}...")
        research_result = researcher.research_company(req.company_name, req.target_year)
        
        # Step 2: Generation
        print(f"[Generator] Building financial model...")
        initial_model = generator.generate_financial_model(
            req.company_name, 
            req.target_year, 
            research_result['synthesized_facts']
        )
        
        # Step 3: Evaluation (Self-Correction Loop - Simplified for Demo)
        # In a real scenario, we'd look up actual DART revenue for the validation year.
        # Here we mock ground truth for the demo based on the company.
        ground_truth = 1000000000000 # Default 1 Trillion KRW
        if "한미반도체" in req.company_name:
            ground_truth = 159000000000  # Approx 159B KRW for Hanmi in 2023
        elif "SK" in req.company_name or "하이닉스" in req.company_name:
            ground_truth = 32700000000000 # Approx 32.7T KRW for SK Hynix in 2023
            
        print(f"[Evaluator] Validating against {req.validation_year} ground truth...")
        evaluation_result = evaluator.calculate_loss_and_feedback(
            req.company_name,
            req.validation_year,
            initial_model,
            ground_truth
        )
        
        # Optional: Step 3.5 - Regenerate based on feedback if loss is too high
        final_model = initial_model
        feedback_str = None
        if "loss_score" in evaluation_result and evaluation_result["loss_score"] > 100:
            print(f"[Generator] Loss too high! Regenerating based on feedback...")
            feedback_str = evaluation_result.get("feedback_for_generator", "")
            refined_prompt = research_result['synthesized_facts'] + "\n\nCRITICAL FEEDBACK FROM EVALUATOR:\n" + feedback_str
            final_model = generator.generate_financial_model(req.company_name, req.target_year, refined_prompt)

        # Step 4: Tech Evaluation & Formatting
        print(f"[Tech Evaluator] Packaging final report...")
        final_payload = tech_evaluator.package_final_report(
            req.company_name,
            req.target_year,
            research_result['synthesized_facts'],
            final_model,
            feedback_str
        )
        
        return {
            "status": "success",
            "data": final_payload
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
