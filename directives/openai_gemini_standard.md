# Directive: OpenAI Client Integration for Gemini

## Goal
Standardize all AI interactions to use the `openai-python` library (OpenAI Client) instead of `google-genai` or other SDKs. This ensures compatibility with the Gemini Router and maintains a unified 3-layer architecture.

## Operating Principles
1. **Never use `google-genai`**: Unless explicitly requested by the USER, always use the `openai` library.
2. **Unified Base URL**: All requests must point to the Gemini OpenAI compatibility layer.
3. **Layer Separation**: AI logic belongs in Layer 3 (Execution scripts). Directives (Layer 1) define the prompt patterns.

## Configuration (OpenAI Client)

### Base Setup
```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
```

## Prompting Patterns

### 1. Basic Text Generation
```python
response = client.chat.completions.create(
    model="gemini-3.1-flash-lite-preview",
    messages=[{"role": "user", "content": "Your prompt here"}]
)
print(response.choices[0].message.content)
```

### 2. Multimodal (Image/Vision)
```python
import base64

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

response = client.chat.completions.create(
    model="gemini-3.1-flash-lite-preview",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encode_image('image.jpg')}"}
                }
            ]
        }
    ]
)
```

### 3. Structured Outputs (JSON)
```python
from pydantic import BaseModel

class AnalysisResult(BaseModel):
    summary: str
    sentiment: str

completion = client.beta.chat.completions.parse(
    model="gemini-3.1-flash-lite-preview",
    messages=[{"role": "user", "content": "Analyze: ..." }],
    response_format=AnalysisResult,
)
print(completion.choices[0].message.parsed)
```

### 4. Gemini-Specific Features (`extra_body`)
For features like **Thinking** (Internal reasoning):
```python
response = client.chat.completions.create(
    model="gemini-3.1-flash-lite-preview",
    messages=[{"role": "user", "content": "solve this math problem"}],
    extra_body={
        "google": {
            "thinking_config": {"include_thoughts": True}
        }
    }
)
```

## Edge Cases & Limitations
- **Token Limits**: Input: 1M tokens, Output: 64k tokens (Flash-Lite).
- **File API**: Use standard GenAI File API for large files (OpenAI bridge upload is limited).
- **Deployment**: Optimized for **Oracle A1 (ARM64)**. Ensure `openai` package is installed in the Oracle image environment.
