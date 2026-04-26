import requests
import json
from google import genai
from .base import BaseAgent

class ResearcherAgent(BaseAgent):
    def __init__(self, client: genai.Client, model_id: str):
        super().__init__(role="Researcher", client=client, model_id=model_id)

    def search_news_urls(self, query: str, max_results: int = 3) -> List[str]:
        """Finds URLs using DuckDuckGo search."""
        urls = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                for res in results:
                    urls.append(res.get("href"))
        except Exception as e:
            print(f"Search failed: {e}")
        return urls

    def scrape_url_with_jina(self, url: str) -> str:
        """Uses Jina Reader API to scrape and convert URL content to Markdown."""
        try:
            jina_url = f"https://r.jina.ai/{url}"
            response = requests.get(jina_url)
            if response.status_code == 200:
                return response.text
            return f"Failed to scrape. Status: {response.status_code}"
        except Exception as e:
            return f"Scraping error: {str(e)}"

    def research_company(self, company_name: str, target_year: int) -> Dict[str, any]:
        """
        Orchestrates the research process:
        1. Search for general business model and products.
        2. Search for financial and ASP/volume news for the target year.
        3. Scrape top URLs and extract context.
        """
        queries = [
            f"{company_name} 주요 제품 ASP 매출 비중 {target_year}",
            f"{company_name} 고객사 수주 공시 {target_year}",
            f"{company_name} 실적 분석 리포트 {target_year}"
        ]
        
        all_urls = []
        for q in queries:
            all_urls.extend(self.search_news_urls(q, max_results=2))
        
        # Deduplicate URLs
        all_urls = list(set(all_urls))[:4] # limit to 4 for time constraints
        
        scraped_data = []
        for url in all_urls:
            content = self.scrape_url_with_jina(url)
            # Truncate content to avoid token overflow if too large
            truncated_content = content[:3000] + "...\n[Truncated]" if len(content) > 3000 else content
            scraped_data.append({"url": url, "content": truncated_content})
            
        # Use Gemini to synthesize facts
        synthesis_prompt = f"""
        You are an expert financial researcher. 
        Analyze the following scraped news/data about {company_name} for the year {target_year}.
        
        Extract the following facts (MUST include the source URL for each fact):
        1. Main products and their ASP (Average Selling Price) if available.
        2. Estimated volume (Q) or CAPEX plans from major clients (Samsung, SK Hynix).
        3. Any mentions of cost, margins, or yield issues.
        
        Scraped Data:
        {json.dumps(scraped_data, ensure_ascii=False, indent=2)}
        
        Format your response as a structured markdown list.
        """
        
        synthesized_facts = self.prompt_model(synthesis_prompt)
        
        return {
            "urls_scraped": all_urls,
            "raw_data": scraped_data,
            "synthesized_facts": synthesized_facts
        }
