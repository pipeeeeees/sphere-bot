from google import genai
from google.genai import types

import json

with open('config/gemini_key.json', 'r') as f:
    data = json.load(f)
    api_key = data['key']

client = genai.Client(api_key=api_key)

# You simply tell the model it has access to 'google_search'
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="What happened in the news in Atlanta today?",
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
)
print(response.text)