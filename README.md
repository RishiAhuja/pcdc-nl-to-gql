<div align="center">

<img src="assets/logo/d4cg-logo.png" alt="D4CG Logo" height="60" />

<br/>
<br/>

# PCDC Cohort Discovery Chatbot

**Natural language → validated Guppy GraphQL filter JSON.**

Describe a patient cohort in plain English. Get a schema-correct, deterministically validated filter back in seconds — ready to paste into the PCDC portal.

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![LangGraph](https://img.shields.io/badge/LangGraph-agentic_pipeline-8B5CF6?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-vector_store-F97316?style=flat-square)](https://www.trychroma.com)

[![Field F1](https://img.shields.io/badge/Field_F1-0.985-22C55E?style=flat-square)](https://github.com/RishiAhuja/pcdc-nl-to-gql)
[![Validator](https://img.shields.io/badge/Validator-100%25_first--pass-22C55E?style=flat-square)](https://github.com/RishiAhuja/pcdc-nl-to-gql)
[![License](https://img.shields.io/badge/License-MIT-gray?style=flat-square)](LICENSE)

</div>

---

## Overview

The PCDC Cohort Discovery Chatbot translates plain-English clinical queries into schema-valid [Guppy](https://github.com/uc-cdis/guppy) GraphQL filter JSON. It is powered by a **10-node LangGraph agentic pipeline** backed by **ChromaDB retrieval** over the full PCDC schema and 1,078 annotated training examples.

**Key capabilities:**

| Feature | Details |
|:--|:--|
| Filter generation | Translates free-form queries into valid nested Guppy JSON |
| Self-healing validation | Catches invalid fields/enums and auto-corrects via targeted retry |
| Clarification loop | Detects staging ambiguity and asks before generating |
| Cohort comparison | Diffs two saved filters field-by-field with a colour-coded view |
| Saved filters | Name, persist, reload, and export any generated filter |
| Export menu | Copy as JSON, GraphQL, aggregation query, or download `.json` |
| Query templates | One-click landing-page prompts for common cohort patterns |
| Reverse explanation | Paste a raw filter JSON; get a plain-English description back |
| Multi-provider LLM | OpenAI · Anthropic · Google — swap with a single env var |

---

## Screenshots

### Filter Generation

<table>
  <tr>
    <td align="center" width="50%">
      <img src="assets/screenshots/landing-page-new.png" alt="Landing page" width="100%"/>
      <br/><sub><b>Clean entry point with query templates</b></sub>
    </td>
    <td align="center" width="50%">
      <img src="assets/screenshots/chat-main.png" alt="Filter generation" width="100%"/>
      <br/><sub><b>Schema-correct Guppy filter with highlighted JSON</b></sub>
    </td>
  </tr>
  <tr>
    <td align="center" colspan="2">
      <img src="assets/screenshots/natural-lang-1.png" alt="Natural language query" width="80%"/>
      <br/><sub><b>Complex multi-condition cohort from a single sentence</b></sub>
    </td>
  </tr>
</table>

### Self-Healing Validation

<table>
  <tr>
    <td align="center" width="50%">
      <img src="assets/screenshots/fake-field-showcase.png" alt="Invalid field detected" width="100%"/>
      <br/><sub><b>Validator catches hallucinated field names before they reach Guppy</b></sub>
    </td>
    <td align="center" width="50%">
      <img src="assets/screenshots/validation-fix.png" alt="Self-healing correction" width="100%"/>
      <br/><sub><b>LLM self-corrects with targeted fix prompt — zero user intervention</b></sub>
    </td>
  </tr>
</table>

### Clarification Flow

<table>
  <tr>
    <td align="center" width="60%">
      <img src="assets/screenshots/clarification.png" alt="Clarification flow" width="100%"/>
      <br/><sub><b>Staging ambiguity detected — one-click disambiguation before generation</b></sub>
    </td>
    <td align="center" width="40%">
      <img src="assets/screenshots/conversation-context.png" alt="Conversation context" width="100%"/>
      <br/><sub><b>Multi-turn refinement — context preserved across follow-up messages</b></sub>
    </td>
  </tr>
</table>

### Saved Filters & Export

<table>
  <tr>
    <td align="center" width="50%">
      <img src="assets/screenshots/save-cohorts.png" alt="Saved filters sidebar" width="100%"/>
      <br/><sub><b>Name and persist any filter — reload or delete from the sidebar</b></sub>
    </td>
    <td align="center" width="50%">
      <img src="assets/screenshots/export-button.png" alt="Export menu" width="100%"/>
      <br/><sub><b>Export as JSON, GraphQL query, aggregation query, or .json download</b></sub>
    </td>
  </tr>
</table>

### Cohort Comparison

<table>
  <tr>
    <td align="center" width="50%">
      <img src="assets/screenshots/comparison-1.png" alt="Cohort comparison diff" width="100%"/>
      <br/><sub><b>Field-by-field diff between two saved cohorts</b></sub>
    </td>
    <td align="center" width="50%">
      <img src="assets/screenshots/comparison-2.png" alt="Comparison detail" width="100%"/>
      <br/><sub><b>Colour-coded view — green added · red removed · amber changed</b></sub>
    </td>
  </tr>
</table>

### General Q&A

<table>
  <tr>
    <td align="center" width="60%">
      <img src="assets/screenshots/general-response.png" alt="General response" width="100%"/>
      <br/><sub><b>Schema and data model questions answered from ChromaDB context</b></sub>
    </td>
  </tr>
</table>

---

## How It Works

Queries pass through a 7-step agentic pipeline built on [LangGraph](https://github.com/langchain-ai/langgraph):

```mermaid
flowchart TD
    Q(["User query"])

    Q --> N1["[1] classify_intent\nfilter request vs. general question"]
    N1 --> N2["[2] retrieve_context\nschema fields + example filters from ChromaDB"]
    N2 --> N3["[3] check_clarity\nask if staging is ambiguous"]
    N3 -->|ambiguous| N8["[8] general_response"]
    N3 -->|clear| N4["[4] generate_filter\n11-rule structured prompt → Guppy JSON"]
    N4 --> N5["[5] validate\nfield names · enum values · nested paths · numeric types"]
    N5 -->|valid| N7["[7] explain_filter\nstream plain-English explanation via SSE"]
    N5 -->|invalid| N6["[6] fix_filter\nself-heal with targeted LLM correction"]
    N6 -->|"retry up to 3×"| N5
    N8 --> END(["SSE response"])
    N7 --> END
```

### System Architecture

```mermaid
flowchart TD
    User(["User"])

    subgraph FE["React Frontend — Vite · TypeScript · Tailwind"]
        UI["ChatWindow · FilterDisplay · ExportMenu\nSavedFiltersSidebar · ComparisonDisplay · ClarificationOptions"]
    end

    subgraph BE["FastAPI Backend"]
        subgraph LG["LangGraph Agent — 10 nodes"]
            A["classify_intent"]
            B["retrieve_context"]
            C["check_clarity"]
            D["generate_filter"]
            E["validate"]
            F["fix_filter"]
            G["explain_filter"]
            H["general_response"]
            I["reverse_explain"]
            J["compare_filters"]
        end
    end

    CHROMA[("ChromaDB\nschema + 1,078 examples")]
    LLM["LLM Provider\nOpenAI · Anthropic · Google"]

    User -- "natural language query" --> FE
    FE -- "POST /chat (SSE)" --> BE

    A --> B --> C
    C -- "ambiguous" --> H
    C -- "clear" --> D --> E
    E -- "valid" --> G
    E -- "invalid" --> F --> E
    A -- "compare" --> J
    A -- "explain" --> I

    B <-.-> CHROMA
    A & C & D & F & I & J <-.-> LLM

    G & H & I & J -- "SSE stream" --> FE --> User
```

---

## Evaluation

Evaluated on a **held-out test split of 270 labelled examples**, stratified 80/20 by consortium with zero ChromaDB contamination. Results below are from a 100-example random sample (SEED=42) to reduce API cost.

| Metric | Score |
|:--|:--|
| Field Precision | **0.986** |
| Field Recall | **0.985** |
| Field F1 | **0.985** |
| Value Accuracy | **1.000** |
| Validator first-pass rate | **100%** (79/79 filters) |
| Self-healing retries needed | **0** |
| Filters with perfect F1 = 1.0 | **94.9%** (75/79) |

> The remaining 21% of queries were correctly deferred to clarification — all involving staging constraints without an explicit disease phase. Once the user selects a phase, the pipeline produces a valid filter immediately. These are not failures; they reflect intended conservative behavior.
>
> Scores reflect in-distribution generalization. Out-of-distribution evaluation (novel consortia, unseen staging systems, free-form clinical phrasing) is a planned next step.

---

## Quick Start

### Prerequisites

| Tool | Version |
|:--|:--|
| Python | ≥ 3.11 |
| Node.js | ≥ 18 |
| Docker | any recent |
| LLM API key | OpenAI / Anthropic / Google |

### 1 · Environment

```bash
cd chatbot
cp .env.example .env
# Set your API key — e.g. OPENAI_API_KEY=sk-...
```

### 2 · ChromaDB

```bash
docker compose up -d
# Verify: curl http://localhost:8100/api/v1/heartbeat
```

### 3 · Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# One-time: ingest schema + 1,078 training examples into ChromaDB
python -m retrieval.ingest

# Start the API server
uvicorn main:app --reload --port 8000
```

### 4 · Frontend

```bash
cd frontend
npm install
npm run dev     # → http://localhost:5173
```

> **Tip — run everything at once:** If you have [mprocs](https://github.com/pvolok/mprocs) installed, `mprocs` from the `chatbot/` directory starts all three services with split-pane output.

---

## Configuration

All settings live in `chatbot/.env`:

| Variable | Default | Description |
|:--|:--|:--|
| `LLM_PROVIDER` | `openai` | `openai` · `anthropic` · `google` |
| `LLM_MODEL` | `gpt-4o` | Model name for the chosen provider |
| `OPENAI_API_KEY` | — | Required when provider is `openai` |
| `ANTHROPIC_API_KEY` | — | Required when provider is `anthropic` |
| `GOOGLE_API_KEY` | — | Required when provider is `google` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model used by ChromaDB |
| `CHROMA_HOST` | `localhost` | ChromaDB host |
| `CHROMA_PORT` | `8100` | ChromaDB port |
| `PROCESSED_GITOPS_JSON` | `../data/processed_gitops.json` | Field → nested-path schema |
| `PROCESSED_SCHEMA_JSON` | `../data/processed_pcdc_schema_prod.json` | Enum → fields schema |
| `ANNOTATED_FILTERS_CSV` | `../data/annotated_amanuensis_search_dump-06-18-2025.csv` | Training examples |

**Switching providers:**

```bash
# Anthropic Claude
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514

# Google Gemini
LLM_PROVIDER=google
LLM_MODEL=gemini-2.0-flash

# OpenAI (default)
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
```

---

## API Reference

### `POST /chat`

Send a message; returns a **Server-Sent Events stream**.

**Request:**
```json
{
  "message": "Show me all AML patients under 5",
  "conversation_id": "optional-uuid",
  "history": []
}
```

**SSE Events:**

| Event | Payload | Description |
|:--|:--|:--|
| `status` | `{"text": "Retrieving context…"}` | Live progress update |
| `token` | `{"text": "Here is the filter…"}` | Streamed explanation text |
| `filter_json` | `{"filter": {…}, "is_valid": true, "explanation": "…"}` | Final validated filter |
| `clarification` | `{"question": "…", "options": ["…"]}` | Disambiguation required |
| `comparison` | `{"differences": […], "summary": "…"}` | Cohort comparison result |
| `error` | `{"text": "…"}` | Unexpected error |
| `done` | `{"conversation_id": "…"}` | Stream complete |

### `GET /health`
Returns `{"status": "ok"}`.

### `GET /conversations/{id}`
Retrieve the full message history for a conversation.

### `DELETE /conversations/{id}`
Delete a conversation from the session store.

### `POST /filters/compare`
Compare two Guppy filter objects field-by-field. Returns a structured diff with added, removed, and changed fields.

### `POST /filters/save` · `GET /filters` · `DELETE /filters/{id}`
CRUD endpoints for saved filters. Filters are stored server-side and associated with a conversation ID.

---

## Evaluation Harness

```bash
cd backend

# Sanity check — no LLM or ChromaDB calls
python -m scripts.preflight

# Run on 100 random held-out examples
python -m scripts.evaluate -n 100 --output results.json

# Run on the full 270 held-out examples
python -m scripts.evaluate --all --output results_full.json

# Deep-dive breakdown of a results file
python -m scripts.analyse_results
```

---

## Acknowledgements

Built for the [Pediatric Cancer Data Commons (PCDC)](https://commons.cri.uchicago.edu/pcdc/) as part of a [Google Summer of Code 2026](https://summerofcode.withgoogle.com/) proposal with [Data for the Common Good (D4CG)](https://d4cg.org/).

This project builds directly on the foundational dataset and architecture established by [Regina Huang's GSoC 2025 implementation](https://github.com/chicagopcdc/GSoC-Cohort-Discovery-Chatbot). The 1,348-example annotated filter set she produced is the backbone of this system's retrieval and evaluation pipeline.