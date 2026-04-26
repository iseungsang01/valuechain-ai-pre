import json
import os
import requests
from bs4 import BeautifulSoup
from google import genai
from typing import List
from datetime import date

from .base import BaseAgent
from .models import GroundingSource

class DataCollectorAgent(BaseAgent):
    def __init__(self, client: genai.Client, model_id: str):
        super().__init__(role="DataCollector", client=client, model_id=model_id)

    def collect_quarterly_data(self, company_name: str, target_quarter: str) -> List[GroundingSource]:
        """
        Collects ASP, Q, or Revenue data points for a specific company in a target quarter.
        Example target_quarter: "2024-Q3"
        """
        # In a real implementation, this would involve tool use with a search engine.
        # To keep the demo focused on the core architecture and feedback loop,
        # we are mocking the return of grounding sources for key companies.
        
        print(f"[{self.role}] Collecting time-bound data for {company_name} in {target_quarter}...")
        
        grounding_sources = []
        
        if "SK Hynix" in company_name or "SK하이닉스" in company_name:
            if target_quarter == "2024-Q3":
                # ASP data (Source: Mocked News)
                grounding_sources.append(GroundingSource(
                    metric_type="ASP",
                    target_quarter="2024-Q3",
                    value=150.0,
                    unit="USD",
                    source_name="메모리 트렌드 뉴스 (Mock)",
                    url="https://memory-news-mock.com/articles/24q3-asp",
                    extraction_date=date(2024, 10, 15)
                ))
                # Revenue data (Source: Mocked Official Release)
                grounding_sources.append(GroundingSource(
                    metric_type="REVENUE",
                    target_quarter="2024-Q3",
                    value=175731.0, # Actual Q3 Revenue was ~17.57 Trillion KRW, mocking part of it
                    unit="KRW_HUNDRED_MILLION",
                    source_name="SK하이닉스 공식 보도자료 (Mock)",
                    url="https://sk-hynix-mock.com/ir/releases/24q3",
                    extraction_date=date(2024, 10, 24)
                ))
        
        elif "TSMC" in company_name:
            if target_quarter == "2024-Q3":
                # Revenue from SK Hynix (implied)
                grounding_sources.append(GroundingSource(
                    metric_type="REVENUE",
                    target_quarter="2024-Q3",
                    value=30000.0,
                    unit="KRW_HUNDRED_MILLION",
                    source_name="Supply Chain Analysis Report (Mock)",
                    url="https://sc-analysis-mock.com/sk-tsmc-edge",
                    extraction_date=date(2024, 11, 1)
                ))
        
        return grounding_sources