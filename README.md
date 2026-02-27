# PCDC Cohort Discovery Chatbot

AI-powered chatbot that converts natural language descriptions of patient cohorts into Guppy-compatible GraphQL filter JSON for the Pediatric Cancer Data Commons.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React Frontend (Vite + Tailwind)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  ChatWindow  │  │ FilterDisplay│  │ Clarification │  │
│  │  + InputBar  │  │ (JSON + copy)│  │   Options     │  │
│  └──────┬───────┘  └──────────────┘  └───────────────┘  │
│         │ SSE (Server-Sent Events)                      │
├─────────┼───────────────────────────────────────────────┤
│  FastAPI Backend                                        │
│         │                                               │
│  ┌──────▼──────────────────────────────┐                │
│  │  LangGraph Agent Pipeline           │                │
│  │  ┌──────────┐    ┌──────────────┐   │                │
│  │  │ Classify  │───▸│  Retrieve   │   │   ┌─────────┐ │
│  │  │ Intent    │    │  Context    │───────▸│ChromaDB │ │
│  │  └──────────┘    └──────┬───────┘   │   │(Docker) │ │
│  │                  ┌──────▼───────┐   │   └─────────┘ │
│  │                  │ Check Clarity│   │                │
│  │                  └──────┬───────┘   │                │
│  │                  ┌──────▼───────┐   │                │
│  │                  │  Generate    │   │                │
│  │                  │  Filter JSON │   │   ┌─────────┐ │
│  │                  └──────┬───────┘   │   │ OpenAI/ │ │
│  │                  ┌──────▼───────┐   │   │Anthropic│ │
│  │                  │  Validate    │───────▸│ Google  │ │
│  │                  └──────┬───────┘   │   └─────────┘ │
│  │                  ┌──────▼───────┐   │                │
│  │                  │  Explain     │   │                │
│  │                  └──────────────┘   │                │
│  └─────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- **Node.js** ≥ 18
- **Python** ≥ 3.11
- **Docker** (for ChromaDB)
- An **OpenAI API key** (or Anthropic/Google)

### 1. Environment Setup

```bash
cd chatbot
cp .env.example .env
# Edit .env and add your API key:
#   OPENAI_API_KEY=sk-...
```

### 2. Start ChromaDB

```bash
docker compose up -d
# Verify: curl http://localhost:8100/api/v1/heartbeat
```

### 3. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ingest schema + examples into ChromaDB (run once)
python -m retrieval.ingest

# Start the API server
uvicorn main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

## Configuration

All config is via environment variables in `chatbot/.env`:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | LLM provider: `openai`, `anthropic`, `google` |
| `LLM_MODEL` | `gpt-4o` | Model name for the chosen provider |
| `OPENAI_API_KEY` | — | Required if provider is `openai` |
| `ANTHROPIC_API_KEY` | — | Required if provider is `anthropic` |
| `GOOGLE_API_KEY` | — | Required if provider is `google` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model for ChromaDB |
| `CHROMA_HOST` | `localhost` | ChromaDB host |
| `CHROMA_PORT` | `8100` | ChromaDB port |
| `PROCESSED_GITOPS_JSON` | `../data/processed_gitops.json` | Path to field→paths schema |
| `PROCESSED_SCHEMA_JSON` | `../data/processed_pcdc_schema_prod.json` | Path to enum→fields schema |
| `ANNOTATED_FILTERS_CSV` | `../data/annotated_amanuensis_search_dump-06-18-2025.csv` | Path to example filters |

## Switching LLM Providers

```bash
# OpenAI (default)
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# Anthropic
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514

# Google
LLM_PROVIDER=google
LLM_MODEL=gemini-2.0-flash
```

## Project Structure

```
chatbot/
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── main.py               # FastAPI app + SSE endpoints
│   ├── config.py              # Pydantic settings
│   ├── models.py              # API request/response models
│   ├── requirements.txt
│   ├── agent/
│   │   ├── llm.py             # Multi-provider LLM factory
│   │   ├── state.py           # LangGraph state definition
│   │   ├── nodes.py           # Agent node functions
│   │   └── graph.py           # LangGraph pipeline assembly
│   ├── retrieval/
│   │   ├── client.py          # ChromaDB client + embeddings
│   │   ├── schema_retriever.py
│   │   ├── example_retriever.py
│   │   └── ingest.py          # Data ingestion script
│   ├── validation/
│   │   └── validator.py       # GQL filter schema validator
│   └── prompts/
│       └── templates.py       # All LLM prompt templates
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── src/
    │   ├── App.tsx
    │   ├── main.tsx
    │   ├── api.ts             # SSE client
    │   ├── types.ts
    │   ├── hooks/
    │   │   └── useChat.ts     # Chat state management
    │   └── components/
    │       ├── Header.tsx
    │       ├── ChatWindow.tsx
    │       ├── MessageBubble.tsx
    │       ├── FilterDisplay.tsx
    │       ├── ClarificationOptions.tsx
    │       └── InputBar.tsx
    └── index.html
```

## API

### `POST /chat`

Send a message. Returns an SSE stream.

**Request:**
```json
{
  "message": "Show me all AML patients under 5",
  "conversation_id": "optional-id",
  "history": []
}
```

**SSE Events:**
| Event | Payload | Description |
|---|---|---|
| `status` | `{"text": "Analyzing..."}` | Processing status updates |
| `token` | `{"text": "Here is..."}` | Text response content |
| `filter_json` | `{"filter": {...}, "is_valid": true, ...}` | Generated GQL filter |
| `clarification` | `{"question": "...", "options": [...]}` | Needs user input |
| `error` | `{"text": "..."}` | Error occurred |
| `done` | `{"conversation_id": "..."}` | Stream complete |

### `GET /health`

Returns `{"status": "ok"}`.

### `GET /conversations/{id}`

Retrieve conversation history.

### `DELETE /conversations/{id}`

Clear a conversation.
