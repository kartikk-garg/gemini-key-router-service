# Gemini API Key Router

A lightweight FastAPI-based proxy service that intelligently routes your Gemini API requests across a pool of API keys. It's designed to help you easily bypass the strict rate limits on the free Gemini API tier by distributing the load across multiple keys.

This router acts as a drop-in **OpenAI-compatible** endpoint. It automatically manages key rotation, tracks rate limits, handles streaming, and seamlessly retries with a new key if one gets exhausted (e.g., encountering a `429 Too Many Requests` error).

## Features
- **OpenAI-Compatible Drop-in Replacement:** Works out of the box with standard OpenAI SDKs and agents.
- **Smart Key Rotation:** Round-robin selection of keys that aren't exhausted.
- **Rate Limit Tracking:** Monitors RPM (Requests Per Minute) and RPD (Requests Per Day).
- **Auto-Reloading:** Add, remove, or update API keys in `keys.json` dynamically without restarting the server.
- **Streaming Support:** Automatically handles `stream: true` chat completions.
- **Health Monitoring:** Built-in `/health` endpoint to monitor key exhaustion and usage statistics.

## Setup

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd gemini-router
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the environment:**
   Copy the example environment file and adjust limits as needed.
   ```bash
   cp .env.example .env
   ```

4. **Add your API Keys:**
   Copy the example keys template and securely paste your actual Gemini API keys.
   ```bash
   cp example_keys.json keys.json
   ```
   *Note: `keys.json` and `.env` are git-ignored to prevent accidental key leaks.*

5. **Start the server:**
   ```bash
   uvicorn main:app --port 8000 --reload
   ```

---

## 🚀 Usage in Your Projects

You can use this router in **any** project, agent framework, or standard SDK (like OpenAI's official Python/JS clients) that supports setting a custom base URL. The router translates OpenAI-format requests into Gemini-compatible API calls automatically since Google's Gemini API supports OpenAI compatibility.

### Using Python OpenAI SDK

```python
from openai import OpenAI

# 1. Point the base_url to your running Gemini Router
# 2. Provide a dummy api_key (the router overrides this with a real one from keys.json)
client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="dummy-key"
)

response = client.chat.completions.create(
    model="gemini-2.0-flash", # Or gemini-1.5-pro, etc.
    messages=[
        {"role": "user", "content": "Hello, how does key rotation work?"}
    ]
)

print(response.choices[0].message.content)
```

### Using in Claude Code, LangChain, AutoGen, or other Agents

Most agent frameworks and command-line tools (like Claude Code) allow you to specify standard OpenAI environment variables. You only need to set these before starting your agent.

```bash
# Provide the URL of your local or remote Gemini Router
export OPENAI_BASE_URL="http://127.0.0.1:8000/v1"

# Provide a dummy key to bypass local validation
export OPENAI_API_KEY="dummy"

# Set your target model
export MODEL_NAME="gemini-2.0-flash" 

# Now run your agent as you normally would!
claude
# or
python my_custom_agent.py
```

## API Endpoints

- `POST /v1/{path}` (e.g. `/v1/chat/completions`) - The standard proxy endpoint for standard generations, multimodal input, and text streaming.
- `GET /health` - View live status, request trackers, and exhaustion states of all keys in your pool.
- `GET /reset-rpd` - Manually resets the Daily request counters to zero.
- `POST /reload` - Manually forces a refresh reading the `keys.json` file.
