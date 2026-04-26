import asyncio
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from agents.data_collector import DataCollectorAgent

async def test_search():
    from google import genai
    gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) if os.getenv("GEMINI_API_KEY") else None
    agent = DataCollectorAgent(client=gemini_client, model_id="gemini-3.1-pro-preview")
    print("Testing data collector for SK Hynix 2024-Q3...")
    
    # We test search specifically
    results = agent._search_quarterly_news("SK Hynix", "2024-Q3")
    print(f"Found {len(results)} search results.")
    for idx, result in enumerate(results):
        print(f"{idx+1}. {result['title']} - {result['url']}")
        
    print("\nTesting full extraction for one hit:")
    if len(results) > 2:
        extracted = agent._extract_metrics_from_search_result("SK Hynix", "2024-Q3", results[2])
        print(f"Extracted {len(extracted)} metrics from result 2.")
        for ex in extracted:
            print(f"- {ex.metric_type}: {ex.value} {ex.unit} from {ex.source_name}")
            
    if len(results) > 3:
        extracted = agent._extract_metrics_from_search_result("SK Hynix", "2024-Q3", results[3])
        print(f"Extracted {len(extracted)} metrics from result 3.")
        for ex in extracted:
            print(f"- {ex.metric_type}: {ex.value} {ex.unit} from {ex.source_name}")

if __name__ == "__main__":
    asyncio.run(test_search())
