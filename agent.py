import os
import sys
import json
import urllib.request
import re
from pathlib import Path

def log_response(text):
    os.makedirs(".ralph", exist_ok=True)
    with open(".ralph/last_response.log", "w", encoding="utf-8") as f:
        f.write(text)

def validate_path(path_str):
    path = Path(path_str)
    if path.is_absolute():
        return False
    if ".." in path.parts:
        return False
    return True

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    prompt = sys.stdin.read()
    
    # Using gemini-1.5-pro-latest as specified in the plan
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-latest:generateContent?key={api_key}"
    
    system_instruction = (
        "You are an autonomous AI coding agent. "
        "Your task is to generate code based on the provided prompt. "
        "You MUST output files using the following format:\n"
        "<file path=\"path/to/file.ext\">\n"
        "content\n"
        "</file>\n"
        "Do not use absolute paths. Do not use '..' in paths. "
        "Only output the file tags and their content. No other text is allowed unless it's outside the tags."
    )
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction}
            ]
        },
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.95,
            "topK": 64,
            "maxOutputTokens": 8192,
            "responseMimeType": "text/plain",
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if "candidates" not in res_data or not res_data["candidates"]:
                print(f"Error: No candidates in response. Full response: {json.dumps(res_data)}")
                sys.exit(1)
                
            text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            log_response(text)
            
            # Parse files
            pattern = r'<file path="([^"]+)">\n?(.*?)\n?</file>'
            matches = re.finditer(pattern, text, re.DOTALL)
            
            found_files = False
            for match in matches:
                found_files = True
                file_path = match.group(1)
                content = match.group(2)
                
                if not validate_path(file_path):
                    print(f"Warning: Skipping invalid path: {file_path}")
                    continue
                
                # Create directories if they don't exist
                parent_dir = os.path.dirname(file_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"Created/Updated file: {file_path}")
            
            if not found_files:
                print("No files found in the response.")
                
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} {e.reason}")
        try:
            error_body = e.read().decode("utf-8")
            print(f"Error body: {error_body}")
        except:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
