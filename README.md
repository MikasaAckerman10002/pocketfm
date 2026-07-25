# AI Character Backend

A minimal FastAPI backend that sends a user's message to Barbie and returns her
text response. This first version intentionally has no memory, speech,
authentication, database, frontend, or agent framework.

## Setup

1. In a terminal, move into the `backend` directory.
2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment template, then add your OpenAI API key:

   ```bash
   cp .env.example .env
   ```

   Replace `your_openai_api_key_here` in `.env` with your key. The app reads
   `OPENAI_API_KEY` from the environment (and loads a local `.env` file for
   development).

5. Start the API:

   ```bash
   uvicorn app:app --reload
   ```

The API is available at `http://127.0.0.1:8000`. Interactive API docs are at
`http://127.0.0.1:8000/docs`.

## Chat endpoint

`POST /chat`

Request body:

```json
{
  "message": "Hi Barbie!"
}
```

Example response:

```json
{
  "reply": "Hi! I'm so happy you're here!"
}
```

Try it with curl:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hi Barbie!"}'
```

## Project layout

```text
backend/
├── app.py              # HTTP endpoint and request/response models
├── agents/barbie.py    # Barbie's system prompt
└── services/llm.py     # OpenAI Chat Completions integration
```
