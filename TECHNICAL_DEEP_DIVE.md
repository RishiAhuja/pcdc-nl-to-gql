# Technical Deep Dive — PCDC Cohort Discovery Chatbot

This document explains in full detail what happens at every layer of the system, from the moment a user presses Enter to the moment the filter JSON is displayed. It covers every class, every function call, every network hop, every prompt, and every decision point.

---

## Table of Contents

1. [System Topology](#1-system-topology)
2. [Request Lifecycle — Step by Step](#2-request-lifecycle--step-by-step)
3. [FastAPI Layer & SSE Streaming](#3-fastapi-layer--sse-streaming)
4. [LangGraph Agent Pipeline](#4-langgraph-agent-pipeline)
   - 4.1 [Node 1 — Intent Classification](#41-node-1--intent-classification)
   - 4.2 [Node 2 — Dual Retrieval](#42-node-2--dual-retrieval)
   - 4.3 [Node 3 — Clarity Check](#43-node-3--clarity-check)
   - 4.4 [Node 4 — Filter Generation](#44-node-4--filter-generation)
   - 4.5 [Node 5 — Schema Validation](#45-node-5--schema-validation)
   - 4.6 [Node 6 — Self-Healing Fix](#46-node-6--self-healing-fix)
   - 4.7 [Node 7 — Explanation](#47-node-7--explanation)
   - 4.8 [Node 8 — General Response](#48-node-8--general-response)
5. [Routing Logic](#5-routing-logic)
6. [ChromaDB Layer — How Retrieval Works](#6-chromadb-layer--how-retrieval-works)
   - 6.1 [Schema Retriever](#61-schema-retriever)
   - 6.2 [Example Retriever](#62-example-retriever)
   - 6.3 [Why Two Separate Retrievers?](#63-why-two-separate-retrievers)
7. [Data Ingestion Pipeline](#7-data-ingestion-pipeline)
8. [Validator — Every Check Explained](#8-validator--every-check-explained)
   - 8.1 [Field Existence Check](#81-field-existence-check)
   - 8.2 [Nested Path Correctness](#82-nested-path-correctness)
   - 8.3 [Enum Value Validation](#83-enum-value-validation)
   - 8.4 [Numeric Type Enforcement](#84-numeric-type-enforcement)
   - 8.5 [Structural Operator Checks](#85-structural-operator-checks)
   - 8.6 [Field Suggestions on Error](#86-field-suggestions-on-error)
9. [Prompt System — Every Template Annotated](#9-prompt-system--every-template-annotated)
10. [LLM Abstraction Layer](#10-llm-abstraction-layer)
11. [Multi-turn Conversation & Clarification Flow](#11-multi-turn-conversation--clarification-flow)
12. [Frontend — SSE Parsing & State Management](#12-frontend--sse-parsing--state-management)
13. [LLM Call Count per Request](#13-llm-call-count-per-request)
14. [Network Call Count per Request](#14-network-call-count-per-request)
15. [Error Handling at Every Layer](#15-error-handling-at-every-layer)
16. [Configuration & Environment Variables](#16-configuration--environment-variables)

---

## 1. System Topology

```
BROWSER (localhost:5173)
  │  React + Vite + Tailwind
  │  useChat hook manages SSE connection
  │
  │  POST /chat  (HTTP with SSE response body)
  │
FASTAPI (localhost:8000)
  │  main.py — receives request, starts agent, streams events
  │
  ├──▶ LangGraph Agent (in-process Python)
  │     │
  │     ├──▶ LLM API  (OpenAI / Anthropic / Google)
  │     │     • Intent classification — 1 call
  │     │     • Clarity check — 0 or 1 call
  │     │     • Filter generation — 1 call
  │     │     • Fix (if invalid) — 0-3 calls
  │     │     • Explanation — 1 call
  │     │
  │     └──▶ ChromaDB (localhost:8100) — HTTP REST
  │           • Query schema collection — 1 call
  │           • Query examples collection — 1 call
  │
  └──▶ Schema files (local disk, loaded at startup)
        • processed_gitops.json   — field → nested_path
        • processed_pcdc_schema_prod.json — enum_value → fields

CHROMADB DOCKER (localhost:8100)
  └── Two persistent collections:
       • pcdc_schema_fields   (75 vectors)
       • pcdc_filter_examples (1,348 vectors)
```

---

## 2. Request Lifecycle — Step by Step

Below is the complete ordered timeline for a typical **query generation** request like *"Show me all AML patients under 5 years old at initial diagnosis"*:

```
T=0ms    Browser: user hits Enter
T=1ms    useChat.sendMessage() builds ChatRequestBody, calls sendChatMessage()
T=2ms    fetch() sends POST /chat  (Content-Type: application/json)
         Body: {
           "message": "Show me all AML patients under 5 years at initial diagnosis",
           "conversation_id": "abc123",
           "history": [...]
         }

T=5ms    FastAPI router receives request
         Retrieves/creates conversation history from _conversations dict
         Appends user message to history
         Builds initial AgentState
         Starts EventSourceResponse (SSE generator begins)

T=6ms    SSE: event=status  data={"text":"Analyzing your request..."}
         (frontend updates status text in loading bubble)

T=7ms    LangGraph graph.invoke() called  ← blocking synchronous call

         ── Node 1: classify_intent ──────────────────────────────
T=8ms    HTTP → OpenAI API (gpt-4o, temperature=0)
         System: INTENT_SYSTEM
         Human:  "Show me all AML patients under 5..."
T=350ms  Response: "query_generation"
         State updated: intent = "query_generation"

         ── Route: query_generation → retrieve_context ────────────

         ── Node 2: retrieve_context ─────────────────────────────
T=351ms  OpenAI Embeddings API call (text-embedding-3-small)
         Input: "Show me all AML patients under 5 years at initial diagnosis"
T=550ms  Returns: 1536-dim float vector
T=551ms  ChromaDB POST /collections/{schema_id}/query
         n_results=10, query_embeddings=[the vector]
T=560ms  Returns: 10 schema fields + metadata + distances
T=561ms  ChromaDB POST /collections/{examples_id}/query
         n_results=5, query_embeddings=[same vector]
T=570ms  Returns: 5 similar real filter sets
         State updated: schema_context, example_context, schema_fields

         ── Node 3: check_clarity ────────────────────────────────
T=571ms  Heuristic scan of user query for staging terms
         "under 5" has no staging ambiguity → needs_clarification = False
         No LLM call made here

         ── Route: no clarification → generate_filter ─────────────

         ── Node 4: generate_filter ──────────────────────────────
T=572ms  HTTP → OpenAI API (gpt-4o, JSON mode, temperature=0)
         System: QUERY_GEN_SYSTEM (12 rules)
         Human:  QUERY_GEN_HUMAN with injected schema_context + example_context + user_query
T=1100ms Response: Raw JSON string
         Parsed → generated_filter dict
         State: generation_attempts = 1

         ── Node 5: validate_filter ──────────────────────────────
T=1101ms GQLFilterValidator.validate() — pure Python, no network
         Checks field names, enum values, nested paths, operators
T=1102ms Result: is_valid=True, fields_used=["disease", "age_at_censor_status"]
         State: is_valid=True, validation_errors=[]

         ── Route: valid → explain_filter ───────────────────────

         ── Node 7: explain_filter ───────────────────────────────
T=1103ms HTTP → OpenAI API (gpt-4o, streaming=False, temperature=0)
         Input: the filter JSON
T=1350ms Response: "Matches subjects diagnosed with AML who were under..."
         State: response_text, filter_result, event_type="filter_json"

T=1351ms LangGraph returns final state

T=1352ms FastAPI reads final state:
         event_type == "filter_json" → SSE: event=token  data={"text":"Matches..."}
T=1353ms SSE: event=filter_json  data={"filter":{...},"is_valid":true,"errors":[],...}
T=1354ms SSE: event=done  data={"conversation_id":"abc123"}

T=1355ms EventSourceResponse closes stream

         Frontend:
T=1356ms token event → updates message.content with explanation text
T=1357ms filter_json event → sets message.filter (FilterDisplay renders)
T=1358ms done event → isLoading=false, status cleared
```

**Total wall-clock time:** ~1.3 seconds  
**LLM calls:** 3 (intent + generation + explanation)  
**Embedding calls:** 1  
**ChromaDB HTTP calls:** 2  
**Disk reads:** 0 (schema files cached at startup in validator)

---

## 3. FastAPI Layer & SSE Streaming

### Entry Point: `POST /chat`

```python
# main.py
@app.post("/chat")
async def chat(request: ChatRequest):
    ...
    return EventSourceResponse(event_stream())
```

`EventSourceResponse` (from `sse-starlette`) wraps an **async generator**. Each `yield` from the generator becomes one SSE frame sent to the browser. The SSE protocol is:

```
event: status\n
data: {"text":"Analyzing..."}\n
\n
event: token\n
data: {"text":"Here is your filter"}\n
\n
event: filter_json\n
data: {"filter":{"AND":[...]},"is_valid":true,...}\n
\n
event: done\n
data: {"conversation_id":"abc123"}\n
\n
```

### Why SSE instead of WebSockets?

- SSE is **unidirectional** (server → client) which is all we need
- Built natively into the browser `fetch()` API — no extra library
- Simple HTTP — works through proxies, firewalls, and Vite's dev proxy
- No handshake cost vs. WebSockets

### Conversation Store

Conversations are stored in a **module-level Python dict** (`_conversations`):

```python
_conversations: dict[str, list[dict]] = {}
```

Each entry is a list of `{"role": "...", "content": "..."}` dicts. On every request the full history grows by 2 entries (user + assistant). This is **in-memory only** — restarts clear all conversations. A production deployment would use Redis.

### The `_pending_context` Hack

When a clarification event happens, the assistant message is stored with a special internal key:

```python
history.append({
    "role": "assistant",
    "content": question,
    "_pending_context": final_state.get("pending_context", ""),
})
```

On the next request the pipeline scans recent history for this key and re-attaches the original partial context to the user's answer, making the next LLM call see both the original query and the user's refinement.

---

## 4. LangGraph Agent Pipeline

The pipeline is a **compiled `StateGraph`**. State is a `TypedDict` (`AgentState`) shared across all nodes, with these fields:

```python
class AgentState(TypedDict, total=False):
    messages: list[dict]          # full conversation history
    user_query: str               # current user message
    conversation_id: str

    intent: str                   # classified intent

    schema_context: str           # formatted text from schema retriever
    example_context: str          # formatted text from example retriever
    schema_fields: list[dict]     # raw field metadata

    generated_json: str           # raw LLM response string
    generated_filter: dict        # parsed filter JSON
    generation_attempts: int      # how many times generate has run

    is_valid: bool                # validator result
    validation_errors: list[str]
    validation_warnings: list[str]
    fields_used: list[str]

    needs_clarification: bool
    clarification_question: str
    clarification_options: list[str]
    pending_context: str          # stashed original query

    response_text: str            # final text for the user
    filter_result: dict | None    # final filter if one was generated
    event_type: str               # "filter_json" | "token" | "clarification"
```

`total=False` means every key is optional — nodes only write the keys they change, and the graph merges partial dicts automatically.

---

### 4.1 Node 1 — Intent Classification

**File:** `agent/nodes.py` → `classify_intent()`

**Purpose:** Determine whether the user wants to:
- Generate a filter (`query_generation`)
- Get information about the portal (`documentation`)
- Answer a previous clarification (`clarification_response`)
- Have a general conversation (`general`)

**LLM call:** 1 call, `temperature=0`, **not** JSON mode — plain text response of exactly one word/phrase.

**Short-circuit heuristic:** If the agent is already mid-clarification (`state["needs_clarification"]` is `True`) and the user sent ≤ 8 words, it is immediately classified as `clarification_response` **without** any LLM call.

```python
if state.get("needs_clarification") and len(user_msg.split()) <= 8:
    return {"intent": "clarification_response"}
```

**Fallback:** If the LLM returns something not in the valid set, it defaults to `query_generation` — the most-common and safest assumption.

```python
valid_intents = {"query_generation", "documentation", "clarification_response", "general"}
if intent not in valid_intents:
    intent = "query_generation"
```

**Output written to state:** `intent`

---

### 4.2 Node 2 — Dual Retrieval

**File:** `agent/nodes.py` → `retrieve_context()`

**Purpose:** Fetch semantically relevant schema fields and real-world filter examples from ChromaDB.

**Network calls:** 1 OpenAI Embeddings call + 2 ChromaDB query calls

**What happens in detail:**

1. If this is a `clarification_response`, the original query is prepended to the answer:
   ```python
   query = f"{state['pending_context']} — {query}"
   # e.g. "AML patients under 5 — Initial Diagnosis"
   ```

2. The query text is embedded via `EmbeddingClient.embed_one()`:
   ```python
   response = self._client.embeddings.create(
       input=[text],
       model="text-embedding-3-small"
   )
   # Returns a 1536-dimensional float vector
   ```

3. Two ChromaDB queries run **sequentially** (same embedding vector reused):
   ```python
   schema_fields = schema_ret.retrieve(query, n_results=10)
   examples = example_ret.retrieve(query, n_results=5)
   ```

4. Results are formatted into **prompt-ready text strings** by `format_for_prompt()`.

**Schema retriever output example** (what gets injected into the prompt):
```
1. **disease** (cancer type)
   Flat field (subject-level)
   Type: enum
   Valid values: [AML, ALL, NBL, RMS, WT, DSRCT, ...]

2. **age_at_censor_status**
   Flat field (subject-level)
   Type: numeric
   Valid values: []
```

**Example retriever output** (5 real filter sets from the 1,348 annotated CSV):
```
Example 1 — "AML patients with relapsed disease in bone marrow"
```json
{"AND": [{"IN": {"disease": ["AML"]}}, {"nested": ...}]}
```
```

**Output written to state:** `schema_context`, `example_context`, `schema_fields`

---

### 4.3 Node 3 — Clarity Check

**File:** `agent/nodes.py` → `check_clarity()`

**Purpose:** Detect genuinely ambiguous queries that cannot be answered correctly without more information.

**Decision flow:**

```
Step 1: Heuristic scan (pure Python, no LLM)
  ┌─────────────────────────────────────────────────────────┐
  │ Does query contain staging terms?                        │
  │ ("stage", "staging", "irs group", "tnm", "m0", "m1")   │
  │                           ↓ yes                         │
  │ Does query also contain phase terms?                     │
  │ ("initial diagnosis", "relapse", "diagnosis")            │
  │                           ↓ no                          │
  │ → needs_clarification = True → proceed to LLM           │
  └─────────────────────────────────────────────────────────┘

Step 2 (only if Step 1 flagged): LLM call to formulate the question
  Uses get_llm_json() — structured JSON output:
  {"question": "At what disease phase is the staging relevant?",
   "options": ["Initial Diagnosis", "Relapse", "Both"]}
```

**Why staging in particular?**  
In Guppy's data model, staging fields (like `inrg_risk_group`, `irs_group`, `tnm_m`) live inside a nested `stagings` table. Each row in that table is tied to a `disease_phase` (e.g., "Initial Diagnosis"). If you query for "stage M1" without specifying the disease phase, the filter will match across ALL phases, which is almost never what a researcher wants. This is the **anchor pattern** described in rule 10 of `QUERY_GEN_SYSTEM`.

**If clarification is needed, the node:**
1. Sets `response_text` to the question
2. Sets `clarification_options` from the LLM response
3. Sets `event_type = "clarification"`
4. Sets `pending_context = user_query` (saves the original query for later)
5. Returns — routing then sends this to `END`, which short-circuits generation entirely

**Output written to state:** `needs_clarification`, `clarification_question`, `clarification_options`, `pending_context`, `event_type`, `response_text`

---

### 4.4 Node 4 — Filter Generation

**File:** `agent/nodes.py` → `generate_filter()`

**Purpose:** The core LLM call that converts the NL query into Guppy GQL JSON.

**LLM call:** 1 call per attempt, `temperature=0`, **JSON mode** (`response_format: json_object`)

**Prompt composition:**
```
System: QUERY_GEN_SYSTEM (12 rules for valid Guppy filter syntax)
Human:  QUERY_GEN_HUMAN (schema context + examples + user query)
```

The `QUERY_GEN_SYSTEM` prompt contains the following rules that guide the LLM:

| Rule | What it enforces |
|------|-----------------|
| 1 | Output ONLY valid JSON — no markdown, no prose |
| 2 | Only use field names from the retrieved schema context |
| 3 | Only use valid enum values listed per field |
| 4 | Categorical fields → `{"IN": {"field": ["value"]}}` |
| 5 | Numeric fields → `{"GTE": {"field": N}}` or `{"LTE": {"field": N}}` |
| 6 | Nested fields → `{"nested": {"path": "table", "AND": [...]}}` |
| 7 | Same nested path → same wrapper |
| 8 | Different nested paths → separate wrappers |
| 9 | Flat fields go at top-level AND |
| 10 | Disease-phase anchor pattern for staging queries |
| 11 | Top-level combinator is always `{"AND": [...]}` |
| 12 | If exact enum unknown, use closest match |

**JSON mode** forces the OpenAI API to return a valid JSON string. If markdown fences are present (sometimes happens despite JSON mode), the node strips them:
```python
if raw_json.startswith("```"):
    lines = [l for l in raw_json.split("\n") if not l.strip().startswith("```")]
    raw_json = "\n".join(lines).strip()
```

**Counter increment:** Each time this node runs, `generation_attempts` increments. This is later checked against `MAX_RETRIES = 3` to prevent infinite loops.

**Output written to state:** `generated_json`, `generated_filter`, `generation_attempts`

---

### 4.5 Node 5 — Schema Validation

**File:** `agent/nodes.py` → `validate_filter()` + `validation/validator.py`

**Purpose:** Deterministically verify the generated filter against the actual PCDC schema. **Zero LLM calls.**

**What is checked** (full breakdown in §8).

**Output written to state:** `is_valid`, `validation_errors`, `validation_warnings`, `fields_used`

---

### 4.6 Node 6 — Self-Healing Fix

**File:** `agent/nodes.py` → `fix_filter()`

**Triggered when:** `is_valid=False` AND `generation_attempts < MAX_RETRIES` (3)

**LLM call:** 1 call, JSON mode, `temperature=0`

**What it receives:**
- The original broken JSON string (`generated_json`)
- The list of validation errors from the validator
- The same schema context (grounding for valid field/enum choices)

**Prompt pattern:**
```
System: VALIDATION_FIX_SYSTEM ("you are fixing a filter, output ONLY JSON")
Human:  Original filter + \n Error list + \n Schema context
```

**After fix, the edge goes back to `validate_filter`** — the fixed filter is re-validated. This creates a **retry loop**:

```
generate_filter → validate_filter → fix_filter → validate_filter → fix_filter → ...
```

Up to `MAX_RETRIES = 3` (so max 3 fix attempts = 4 total validation checks). After 3 failed attempts, the router sends the (still-invalid) filter to `explain_filter` anyway, and the frontend displays it with `isValid=false` and the error list.

**Output written to state:** `generated_json`, `generated_filter`

---

### 4.7 Node 7 — Explanation

**File:** `agent/nodes.py` → `explain_filter()`

**Purpose:** Generate a 1-2 sentence plain English summary of what the filter does.

**LLM call:** 1 call, `streaming=False`, `temperature=0`

**Input:** The complete filter JSON as a formatted string.

**Output example:**
> "Matches subjects diagnosed with Acute Myeloid Leukemia (AML) who were under 5 years of age, assessed at initial diagnosis."

This text is what gets sent as the `token` SSE event before the `filter_json` event.

**Output written to state:** `response_text`, `filter_result` (the validated filter), `event_type = "filter_json"`

---

### 4.8 Node 8 — General Response

**File:** `agent/nodes.py` → `general_response()`

**Triggered when:** intent is `documentation` or `general`

**LLM call:** 1 call, `streaming=False`, `temperature=0`

Uses `GENERAL_SYSTEM` / `GENERAL_HUMAN` prompts. The system prompt reminds the LLM it's an assistant for the PCDC portal, and if the user wants filters, it should guide them to describe the cohort.

**Output written to state:** `response_text`, `event_type = "token"`, `filter_result = None`

---

## 5. Routing Logic

The graph has three conditional routing points:

### After Intent Classification

```
intent == "query_generation"     → retrieve_context
intent == "clarification_response" → retrieve_context
intent == "documentation"        → general_response
intent == "general"              → general_response
```

### After Clarity Check

```
needs_clarification == True  → END (sends clarification event)
needs_clarification == False → generate_filter
```

### After Validation

```
is_valid == True                          → explain_filter
is_valid == False AND attempts < 3       → fix_filter
is_valid == False AND attempts >= 3      → explain_filter (with errors)
```

**Graph edges drawn as ASCII:**

```
classify_intent ──────────────────────────────────── general_response ── END
     │                                                       ↑
     ↓ (query_generation / clarification_response)           │
retrieve_context                                 (documentation / general)
     │
     ↓
check_clarity ──── END (if needs clarification)
     │
     ↓ (clear)
generate_filter
     │
     ↓
validate_filter ───────────────────────────── explain_filter ── END
     │                      ↑                     ↑
     ↓ (invalid, attempts<3) │                     │ (max retries)
   fix_filter ───────────────┘                     │
     └─────────────────────────────────────────────┘
```

---

## 6. ChromaDB Layer — How Retrieval Works

ChromaDB is a **vector database** — it stores floating-point embeddings alongside document text and metadata, and answers similarity queries.

### Collection Structure

**`pcdc_schema_fields` collection (75 vectors)**

Each document describes one PCDC field:
```
"disease: Cancer Type. This is a subject-level (flat) field.
 Valid values include: AML, ALL, NBL, RMS, WT, ..."
```

Metadata stored per document:
```json
{
  "field_name": "disease",
  "nested_path": "",          // empty = flat
  "field_type": "enum",
  "valid_values": "[\"AML\", \"ALL\", \"NBL\", ...]"
}
```

**`pcdc_filter_examples` collection (1,348 vectors)**

Each document is a natural-language description from the `llm_result` column of the annotated CSV.

Metadata stored per document:
```json
{
  "name": "AML relapsed bone marrow",
  "graphql": "{\"AND\":[{\"IN\":{\"disease\":[\"AML\"]}}, ...]}"
}
```

### How a Query Works

When `SchemaRetriever.retrieve("AML patients under 5")` is called:

1. Call `EmbeddingClient.embed_one("AML patients under 5")`
   - HTTP POST to OpenAI Embeddings API
   - Returns: 1536-float vector e.g. `[0.023, -0.041, 0.187, ...]`

2. Call `ChromaHTTPClient.query(collection_id, [embedding], n_results=10)`
   ```
   POST http://localhost:8100/api/v1/collections/{id}/query
   Body: {
     "query_embeddings": [[0.023, -0.041, ...]],
     "n_results": 10,
     "include": ["documents", "metadatas", "distances"]
   }
   ```

3. ChromaDB runs **HNSW approximate nearest neighbor search** over its 75 stored vectors
4. Returns the 10 most similar field descriptions by cosine distance

5. The results are built into `SchemaField` dataclasses and formatted into a prompt string

### Cosine Distance vs. Similarity

ChromaDB returns `distances` not `similarities`. For cosine space:
- `distance = 0` → identical vectors
- `distance = 2` → completely opposite vectors
- `distance ≈ 0.3-0.6` → typical relevant matches

The retrievers don't filter by distance threshold — they always return the top-N. This ensures something is always retrieved even for unusual queries.

### 6.1 Schema Retriever

```python
class SchemaRetriever:
    def retrieve(self, query: str, n_results: int = 8) -> list[SchemaField]:
        ...
    def format_for_prompt(self, fields: list[SchemaField]) -> str:
        ...
```

`retrieve()` returns `SchemaField` dataclasses. Each has:
- `field_name` — e.g. `"disease"`
- `nested_path` — e.g. `"stagings"` or `""` for flat
- `field_type` — `"enum"` or `"numeric"`
- `valid_values` — list of valid enum strings (empty for numeric)
- `description` — the original embedded document text

`format_for_prompt()` converts these into a numbered, human-readable list injected into `QUERY_GEN_HUMAN`. This tells the LLM exactly which fields are available and what values are allowed, grounding the generation.

### 6.2 Example Retriever

```python
class ExampleRetriever:
    def retrieve(self, query: str, n_results: int = 5) -> list[FilterExample]:
        ...
    def format_for_prompt(self, examples: list[FilterExample]) -> str:
        ...
```

`retrieve()` returns `FilterExample` dataclasses with the actual GraphQL filter JSON from the database. `format_for_prompt()` wraps each in a JSON code block with the NL description as a label.

These examples serve as **few-shot in-context demonstrations** — the LLM sees real, working filter structures and mimics their patterns.

### 6.3 Why Two Separate Retrievers?

| Schema Collection | Examples Collection |
|------------------|---------------------|
| Answers: "what fields exist?" | Answers: "what does a valid filter *look like*?" |
| 75 documents | 1,348 documents |
| Contains field definitions and enum lists | Contains real-world filter structures |
| Prevents hallucinated field names | Prevents hallucinated JSON structure |
| Updated only if schema changes | Can grow as more filters are collected |

Together they give the LLM: *what to put* (schema fields) + *how to structure it* (examples).

---

## 7. Data Ingestion Pipeline

**File:** `retrieval/ingest.py` — run once via `python -m retrieval.ingest`

### Step 1: Load source files

```python
processed_gitops = json.load(open("processed_gitops.json"))
# Structure: {"disease": [], "age_at_censor_status": [], "inrg_risk_group": ["stagings"], ...}
# empty list = flat field, ["stagings"] = nested in "stagings" table

processed_schema = json.load(open("processed_pcdc_schema_prod.json"))
# Structure: {"AML": ["disease", "primary_site"], "Initial Diagnosis": ["disease_phase"], ...}
# enum_value → [field_names] that can hold this value
```

### Step 2: Build reverse map

```python
# processed_schema is enum→fields; we need field→enums
field_to_enums = defaultdict(list)
for enum_val, field_names in processed_schema.items():
    for field_name in field_names:
        if field_name in processed_gitops:   # only include configured fields
            field_to_enums[field_name].append(enum_val)
```

### Step 3: Build field description strings

For each of the 75 fields, create a rich text document:
```python
"disease: Cancer Type. This is a subject-level (flat) field.
 Valid values include: AML, ALL, NBL, RMS, WT, DSRCT, EWS, OS, GCT,
 HL, LCH, MDS, ML, NBL, NPC, NRSTS, NHL..."
```

Numeric fields get different wording:
```python
"age_at_censor_status: Age At Censor Status.
 This is a subject-level (flat) field.
 This is a numeric field. Use GTE/LTE operators for ranges."
```

### Step 4: Embed and upsert in batches of 50

```python
BATCH = 50
for i in range(0, len(ids), BATCH):
    batch_docs = documents[i:i+BATCH]
    batch_embeddings = embedder.embed(batch_docs)  # 1 OpenAI API call per batch
    chroma.upsert(collection_id, ids[i:i+BATCH], batch_embeddings, batch_docs, metadatas[i:i+BATCH])
```

For 75 schema fields: **2 embedding API calls** (50 + 25)
For 1,348 examples: **27 embedding API calls** (27 × 50)

Using `upsert` rather than `add` means re-running the script won't fail on duplicate IDs — it updates in place.

### Step 5: CSV ingestion

The annotated CSV (`annotated_amanuensis_search_dump-06-18-2025.csv`) has columns:
- `name` — human label for the filter set
- `filter_object` — the UI filter JSON (not used)
- `graphql_object` — the actual Guppy GQL filter JSON ← this is stored
- `llm_result` — an NL description of what the filter does ← this is embedded

Rows are skipped if:
- `graphql_object` is empty, `{}`, or `"null"`
- `graphql_object` fails JSON parsing
- `llm_result` is empty

Of 1,500 rows → **1,348 pass** all filters.

---

## 8. Validator — Every Check Explained

**File:** `validation/validator.py` — `GQLFilterValidator`

The validator loads both schema files into memory once (via `@lru_cache()` on `get_validator()`). It holds:

```python
self._field_to_paths: dict[str, list[str]]
# {"disease": [], "inrg_risk_group": ["stagings"], ...}
# field_name → list of nested table names (empty = flat)

self._field_to_enums: dict[str, set[str]]
# {"disease": {"AML", "ALL", "NBL", ...}, ...}
# field_name → set[valid_enum_values]

self._all_fields: set[str]
# Set of all valid field names (75 fields + "disease_phase" special case)
```

### 8.1 Field Existence Check

Every field name that appears inside `IN`, `=`, `!=`, `GT`, `GTE`, `LT`, `LTE` is checked against `self._all_fields`:

```python
if field_name not in self._all_fields:
    result.errors.append(
        f"Unknown field: '{field_name}'. Did you mean one of: {self._suggest_field(field_name)}?"
    )
```

**This is an ERROR** (causes `is_valid=False`), not a warning.

Example — if LLM generates `{"IN": {"tumour_type": ["AML"]}}` (typo), the validator catches `tumour_type` as unknown and suggests `tumor_classification` or `tumor_type_original`.

### 8.2 Nested Path Correctness

When a field appears inside a `{"nested": {"path": "stagings", "AND": [...]}}` block, the validator checks that the field actually belongs to the `stagings` table:

```python
if nested_path:
    expected_paths = self._field_to_paths.get(field_name, [])
    if expected_paths and nested_path not in expected_paths:
        if field_name != "disease_phase":  # anchor is always ok
            result.errors.append(
                f"Field '{field_name}' should be in nested path "
                f"'{expected_paths}', but found in '{nested_path}'"
            )
```

**Special case:** `disease_phase` is never flagged for wrong nesting because it serves as the **anchor field** — it can appear in any nested table to restrict which rows are matched within that table.

**This is an ERROR.**

### 8.3 Enum Value Validation

For enum fields, each value in an `IN` operator is checked against the known valid values:

```python
valid_enums = self._field_to_enums.get(field_name)
if valid_enums:
    for v in values:
        if v not in valid_enums:
            result.warnings.append(f"Value '{v}' may not be valid for field '{field_name}'")
```

This is deliberately a **WARNING** (not an error) because:
- The schema data may not include all valid values (some come from newer studies)
- The LLM may use a slightly different but semantically equivalent name
- We don't want to block users for minor casing differences

### 8.4 Numeric Type Enforcement

For comparison operators (`GT`, `GTE`, `LT`, `LTE`), the value must be numeric:

```python
if not isinstance(num, (int, float)):
    result.errors.append(
        f"Comparison value for '{field_name}' must be numeric, got {type(num).__name__}"
    )
```

**This is an ERROR.** A common LLM mistake is to generate `{"GTE": {"age_at_censor_status": "5 years"}}` (string instead of number).

Note: Age fields are stored in **days** in PCDC's data model. So "5 years" should be `1825` (days). The validator doesn't enforce the days-vs-years conversion — that's a prompt concern.

### 8.5 Structural Operator Checks

The validator walks the nested dict tree via `_check_node()`:

| Operator key | Expected value type | Error if wrong |
|---|---|---|
| `AND`, `OR` | list | "must be a list" |
| `nested` | dict with `path` key | "must have a 'path' key" |
| `IN`, `in` | dict of field→list | "IN values must be a list" |
| `=`, `eq`, `EQ`, `!=` | dict | "Equality value must be a dict" |
| `>`, `>=`, etc. | dict with numeric values | "must be numeric" |
| anything else | — | warning: "Unknown operator" |

The tree walk recurse into `AND`/`OR` arrays and into `nested` contents, so deeply nested structures are fully validated.

### 8.6 Field Suggestions on Error

Instead of just "Unknown field", the validator does a simple substring match to suggest correct names:

```python
def _suggest_field(self, wrong_name: str) -> str:
    lower = wrong_name.lower()
    suggestions = [
        f for f in self._all_fields
        if lower in f.lower() or f.lower() in lower
    ]
    return ", ".join(sorted(suggestions)[:5])
```

These suggestions are included in the error message passed to the self-healing LLM call, giving it the correct field names to use.

---

## 9. Prompt System — Every Template Annotated

**File:** `prompts/templates.py`

### `INTENT_SYSTEM`

Tells the LLM to output **exactly one** of 4 category strings. Four examples are given in the system prompt. No chain-of-thought, no explanation — just the category label.

The key design choice: **documentation** and **general** are separate. "What's INRG?" → documentation. "Hello!" → general. Both route to the same `general_response` node, but the intent label is available for future routing if needed.

### `QUERY_GEN_SYSTEM`

The most critical prompt. 12 rules covering:
- Output format (pure JSON only)
- Data model rules (field names, enum values)
- Structural rules (IN operator, GTE/LTE, nested wrappers)
- Grouping rules (same-path fields in same wrapper)
- The disease-phase anchor pattern (critical for staging queries)

The anchor pattern (rule 10) is particularly important:
```
{"nested": {"path": "stagings", "AND": [
  {"AND": [
    {"IN": {"disease_phase": ["Initial Diagnosis"]}},  ← anchor
    {"AND": [
      ...your staging filters here...
    ]}
  ]}
]}}
```
This pattern ensures that staging values are only matched on rows where the disease phase is "Initial Diagnosis", not across all phases.

### `QUERY_GEN_HUMAN`

Three-section prompt injected at runtime:
```
## RELEVANT FIELDS (from the PCDC schema)
{schema_context}            ← 10 formatted field descriptions

## SIMILAR REAL EXAMPLES
{example_context}           ← 5 real filter JSONs as code blocks

## USER QUERY
"{user_query}"

## OUTPUT
Generate the filter JSON...
```

The section headers explicitly separate the three types of information so the LLM can find each one quickly.

### `VALIDATION_FIX_SYSTEM`

Minimal prompt — "you are fixing a broken filter, output ONLY JSON". Intentionally brief to not distract from the task.

### `VALIDATION_FIX_HUMAN`

Shows the LLM:
1. The broken JSON (wrapped in a code block)
2. A bullet-list of validation errors
3. The available schema fields

Critically, the field suggestions from the validator are embedded in the error messages, so the LLM sees "Unknown field 'tumour_type'. Did you mean one of: tumor_classification, tumor_type_original?" — it has everything it needs to fix the error without needing new retrieval.

### `CLARIFICATION_SYSTEM` / `CLARIFICATION_HUMAN`

Instructs the LLM to:
1. Identify the **single most critical** missing piece of information
2. Return JSON with `question` and `options` keys
3. Give 2-5 concrete options the user can click

Context is provided about PCDC specifics: disease phases, consortia names, age-in-days storage, etc. This prevents the LLM from asking generic questions.

### `EXPLANATION_SYSTEM` / `EXPLANATION_HUMAN`

"Be concise — 1-2 sentences max." This prevents the LLM from writing paragraphs. The explanation is shown alongside the filter, not as a substitute for it.

### `GENERAL_SYSTEM`

Primes the LLM as a PCDC portal assistant. Crucially includes: "If the user wants to create a filter, suggest they describe the cohort they need." — this ensures the bot doesn't just answer documentation questions but actively redirects toward filter generation.

---

## 10. LLM Abstraction Layer

**File:** `agent/llm.py`

Two factory functions, both `@lru_cache()`:

```python
get_llm(*, streaming: bool = True) → BaseChatModel
get_llm_json(*, streaming: bool = False) → BaseChatModel
```

**`get_llm`** is used for:
- Intent classification (streaming=False — short response, speed matters)
- Explanation generation (streaming=False — small output)
- General response (streaming=False — SSE token streaming not implemented in current backend)

**`get_llm_json`** is used for:
- Filter generation — needs structured JSON output
- Clarification question — needs `{"question": ..., "options": [...]}` JSON
- Self-healing fix — needs JSON output

### Provider Matrix

| Provider | `get_llm_json` mode | Notes |
|----------|--------------------|-|
| OpenAI | `response_format: {"type": "json_object"}` | Guaranteed valid JSON |
| Anthropic | Falls back to `get_llm()` | Relies on prompt instructions |
| Google | Falls back to `get_llm()` | Relies on prompt instructions |

For non-OpenAI providers, JSON reliability depends entirely on the model following the prompt instructions. The prompt already says "Output ONLY valid JSON" but it's not enforced at the API level.

### `@lru_cache()` Behavior

The LRU cache is keyed on **all arguments** including `streaming`. So `get_llm(streaming=False)` and `get_llm(streaming=True)` are two separate cached instances. This means:
- The model object is created exactly once per `(provider, streaming)` combination
- No cold-start cost after the first call to each variant
- But `lru_cache` is not thread-safe for the initialization step — this is fine for the current single-worker Uvicorn setup

---

## 11. Multi-turn Conversation & Clarification Flow

### Normal Multi-turn

Every call to `POST /chat` includes:
```json
{"message": "...", "conversation_id": "abc123", "history": [...]}
```

The `history` array is the full prior conversation. The agent's `classify_intent` node does NOT use the history for classification — it only looks at the current `user_query`. This is intentional: we want intent to be determined by what the user just said, not by the whole conversation thread.

However, the generation prompt (`QUERY_GEN_HUMAN`) also has access to `messages` in state — future nodes could use the full history to resolve pronouns like "the same filter but for females" if implemented.

### Clarification Round-trip

Turn 1: User asks an ambiguous staging query
```
User: "Find relapsed bone marrow patients at stage 4"
```

1. `check_clarity` fires: "stage 4" found, no disease phase
2. `clarification_question = "At which disease phase should the stage 4 apply?"`
3. `clarification_options = ["Initial Diagnosis", "Relapse", "Both"]`
4. `pending_context = "Find relapsed bone marrow patients at stage 4"`
5. SSE event: `clarification` → frontend shows clickable buttons
6. History entry saved:
   ```python
   {"role": "assistant", "content": "At which disease phase...", "_pending_context": "Find relapsed..."}
   ```

Turn 2: User clicks "Relapse"
```
User: "Relapse"
```

1. `classify_intent`: ≤ 8 words + `needs_clarification` was set → returns `clarification_response` immediately (no LLM)
2. `retrieve_context`: merges query: `"Find relapsed bone marrow patients at stage 4 — Relapse"`
3. Full generation proceeds with the merged, disambiguated query

### Why stash `pending_context`?

Without it, turn 2 would only have "Relapse" as the query — useless in isolation. The `_pending_context` key in the stored history is a lightweight way to carry the original query forward without changing the history format that the LLM sees (messages with `_pending_context` are stripped of that key before being shown to the LLM).

---

## 12. Frontend — SSE Parsing & State Management

**Files:** `src/api.ts`, `src/hooks/useChat.ts`

### SSE Parsing in `api.ts`

The browser's native `EventSource` API doesn't allow `POST` bodies — it only does GET. So instead we use `fetch()` with streaming body:

```javascript
const response = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: controller.signal,
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // split on newlines, parse event: / data: lines
}
```

**Critical detail:** `{ stream: true }` in `TextDecoder.decode()` preserves incomplete multi-byte characters across chunk boundaries — important for non-ASCII content in filter values.

The manual SSE parser:
1. Reads `event: <name>` lines to set `currentEvent`
2. Reads `data: <json>` lines, parses as JSON, calls `onEvent(currentEvent, data)`
3. Empty lines reset `currentEvent` to `"message"`

### State Management in `useChat.ts`

The hook maintains a `messages` array. Two key operations:

**Append** (for new messages):
```typescript
setMessages(prev => [...prev, msg]);
```

**Update last assistant message** (for streaming tokens and events):
```typescript
setMessages(prev => {
    const idx = prev.length - 1;
    if (idx < 0 || prev[idx].role !== "assistant") return prev;
    const copy = [...prev];
    copy[idx] = updater(copy[idx]);
    return copy;
});
```

This immutable pattern ensures React re-renders correctly on each event.

### Event Handler Map

| SSE Event | What `useChat` does |
|---|---|
| `status` | Sets `message.statusText` (shows in loading bubble alongside dots) |
| `token` | Appends `data.text` to `message.content` (character-by-character streaming effect) |
| `filter_json` | Sets `message.filter: FilterResult` (renders FilterDisplay component) |
| `clarification` | Sets `message.content` + `message.clarification` (renders ClarificationOptions) |
| `error` | Appends error text to `message.content` with ⚠️ prefix |
| `done` | Sets `message.isLoading = false`, clears `statusText`, sets `isLoading = false` |

### Clarification Button → New Message

When a user clicks a clarification option button:
```typescript
const selectClarification = (option: ClarificationOption) => {
    sendMessage(option.label);  // treats the option label as a normal message
};
```

This creates a new user message bubble and a new assistant bubble, and starts a new SSE stream. The full message history is passed along, so the server can pick up `_pending_context`.

### Abort / Cancel

```typescript
const controller = sendChatMessage(body, onEvent);
abortRef.current = controller;
// ...
const cancelRequest = () => {
    abortRef.current?.abort();  // triggers AbortError in fetch()
    setIsLoading(false);
};
```

The `AbortController` signal is passed to `fetch()`. When aborted, the `fetch` throws `DOMException(AbortError)` which is caught and silently ignored. The in-progress assistant message bubble stays with whatever tokens arrived before cancellation.

---

## 13. LLM Call Count per Request

| Request type | Node 1 | Node 2 (embed) | Node 3 | Node 4 | Node 5 | Node 6 | Node 7 | Total |
|---|---|---|---|---|---|---|---|---|
| Clear filter query | 1 | 1 | 0 | 1 | 0 | 0 | 1 | **3 LLM calls** |
| Clear query (fix once) | 1 | 1 | 0 | 1 | 0 | 1 | 1 | **4 LLM calls** |
| Clear query (max fixes) | 1 | 1 | 0 | 1 | 0 | 3 | 1 | **6 LLM calls** |
| Ambiguous (needs clarification) | 1 | 1 | 1 | 0 | 0 | 0 | 0 | **2 LLM calls** |
| Clarification turn 2 | 0 | 1 | 0 | 1 | 0 | 0 | 1 | **2 LLM calls** |
| General question | 1 | 0 | 0 | 0 | 0 | 0 | 0 | **1 LLM call** *(general_response)* |

Note: The embedding call is to OpenAI Embeddings API (not a chat model) — it's much cheaper and faster (~50ms, ~0.00002 USD per call with `text-embedding-3-small`).

---

## 14. Network Call Count per Request

For a typical clear filter query:

| # | Destination | Type | Payload | Latency |
|---|---|---|---|---|
| 1 | OpenAI Chat API | POST | Intent prompt (small) | ~200ms |
| 2 | OpenAI Embeddings API | POST | 1 text string → 1536-float vector | ~100ms |
| 3 | ChromaDB `/collections` | POST | Schema collection name | ~5ms |
| 4 | ChromaDB `/query` | POST | 1 query embedding, n=10 | ~10ms |
| 5 | ChromaDB `/collections` | POST | Examples collection name | ~5ms |
| 6 | ChromaDB `/query` | POST | same embedding, n=5 | ~10ms |
| 7 | OpenAI Chat API | POST | Generation prompt (large — schema + examples + query) | ~600ms |
| 8 | OpenAI Chat API | POST | Explanation prompt (filter JSON) | ~300ms |

**Total external calls: 8** (3 to OpenAI, 2 pair to ChromaDB)  
**Total latency: ~1.2-1.5 seconds** (dominated by LLM calls, which run sequentially)

ChromaDB calls 3 and 5 (`POST /collections` with `get_or_create=true`) are technically unnecessary on every query — ideally the collection IDs would be cached. The reason they're called is that `get_or_create_collection()` is the only working endpoint in ChromaDB 0.6.3 (the `GET /collections/{name}` endpoint has a bug). These add ~10ms total.

---

## 15. Error Handling at Every Layer

### In the Agent Nodes

**`generate_filter`** — if `json.loads()` fails:
```python
return {
    "generated_filter": {},
    "is_valid": False,
    "validation_errors": [f"Invalid JSON from LLM: {e}"],
    "generation_attempts": state.get("generation_attempts", 0) + 1,
}
```
This writes an empty filter with a prefilled error, which causes `validate_filter` to see `is_valid=False` and trigger a fix attempt.

**`fix_filter`** — if the fix produces invalid JSON:
```python
return {
    "generated_filter": {},
    "is_valid": False,
    "validation_errors": [f"Fix attempt produced invalid JSON: {e}"],
}
```
Same pattern — goes back to validate, which goes to another fix, up to MAX_RETRIES.

**`explain_filter`** — if filter is empty:
```python
if not gql_filter:
    return {"response_text": "I generated a filter but it appears to be empty."}
```

### In the FastAPI Layer

```python
try:
    final_state = agent_graph.invoke(initial_state)
    ...
except Exception as e:
    logger.exception("Agent error")
    yield _sse_event("error", {"text": str(e)})
    yield _sse_event("done", {"conversation_id": conv_id})
```

Any unhandled exception in the entire agent pipeline (including ChromaDB timeouts, OpenAI rate limits, network failures) is caught here. The user sees an error message, but the SSE stream closes cleanly.

### In the ChromaDB Client

```python
r.raise_for_status()
```

`httpx` raises `HTTPStatusError` on 4xx/5xx responses. This propagates up to the FastAPI exception handler above.

### In the Frontend SSE Parser

```typescript
try {
    const data = JSON.parse(raw);
    onEvent(currentEvent, data);
} catch {
    onEvent(currentEvent, raw);  // fallback: pass raw string
}
```

If the SSE data isn't valid JSON, the raw string is passed through. Most event handlers check for `.text` property specifically, so they'd get `undefined` but wouldn't crash.

### Abort Error

```typescript
if (err instanceof DOMException && err.name === "AbortError") return;
```

Abort is silently swallowed — it's not an error, it's a user action.

---

## 16. Configuration & Environment Variables

**File:** `backend/config.py` — `Settings` class (`pydantic-settings`)

Variables are loaded from `chatbot/.env` and validated at startup:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
    )
```

### Path Resolution

Data file paths in `.env` are stored relative to the workspace root (`../...`). The `resolve_path()` method resolves them relative to the config file's directory:

```python
def resolve_path(self, raw_path: str) -> str:
    base = Path(__file__).parent.parent  # → chatbot/
    p = Path(raw_path)
    if not p.is_absolute():
        p = (base / p).resolve()
    return str(p)
```

This means `.env` can use `../GSoC-Cohort-Discovery-Chatbot/schema/processed_gitops.json` and it works regardless of the current working directory when the server starts.

### `@lru_cache()` on `get_settings()`

```python
@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

Settings are loaded once and cached. This means:
1. The `.env` file is parsed exactly once at first call
2. All subsequent calls share the same `Settings` instance
3. Changes to `.env` require a server restart

### All Variables

| Variable | Type | Default | Used in |
|---|---|---|---|
| `LLM_PROVIDER` | str | `openai` | `llm.py` — selects LangChain backend |
| `LLM_MODEL` | str | `gpt-4o` | `llm.py` — model name |
| `OPENAI_API_KEY` | str | `""` | `llm.py`, `retrieval/client.py` |
| `ANTHROPIC_API_KEY` | str | `""` | `llm.py` |
| `GOOGLE_API_KEY` | str | `""` | `llm.py` |
| `EMBEDDING_MODEL` | str | `text-embedding-3-small` | `retrieval/client.py` |
| `CHROMA_HOST` | str | `localhost` | `retrieval/client.py` — ChromaDB HTTP base URL |
| `CHROMA_PORT` | int | `8100` | `retrieval/client.py` |
| `PROCESSED_GITOPS_JSON` | str | — | `retrieval/ingest.py`, `validation/validator.py` |
| `PROCESSED_SCHEMA_JSON` | str | — | `retrieval/ingest.py`, `validation/validator.py` |
| `FILTER_SETS_CSV` | str | — | `retrieval/ingest.py` |
| `BACKEND_HOST` | str | `0.0.0.0` | `main.py` `uvicorn` run |
| `BACKEND_PORT` | int | `8000` | `main.py` `uvicorn` run |
| `CORS_ORIGINS` | str | `http://localhost:5173` | `main.py` CORS middleware |

---

## Appendix: Complete Data Flow Diagram

```
User types "AML patients under 5 at initial diagnosis"
    │
    ▼ POST /chat
FastAPI receives ChatRequest
    │
    ├─ SSE: status "Analyzing..."
    │
    ▼ LangGraph.invoke(initial_state)
    │
    ├─[Node 1] classify_intent
    │   └─ OpenAI call → "query_generation"
    │
    ├─[Route] → retrieve_context
    │
    ├─[Node 2] retrieve_context
    │   ├─ OpenAI embed("AML patients under 5...") → [1536 floats]
    │   ├─ ChromaDB query(schema) → 10 field definitions
    │   └─ ChromaDB query(examples) → 5 real filter JSONs
    │
    ├─[Node 3] check_clarity
    │   └─ Heuristic scan → no staging terms → needs_clarification=False
    │
    ├─[Route] → generate_filter
    │
    ├─[Node 4] generate_filter
    │   └─ OpenAI JSON call(schema+examples+query) →
    │      {"AND": [
    │        {"IN": {"disease": ["AML"]}},
    │        {"LTE": {"age_at_censor_status": 1825}},
    │        {"nested": {"path": "stagings", "AND": [
    │          {"AND": [
    │            {"IN": {"disease_phase": ["Initial Diagnosis"]}},
    │            ...
    │          ]}
    │        ]}}
    │      ]}
    │
    ├─[Node 5] validate_filter
    │   ├─ Check: "disease" ∈ all_fields? ✓
    │   ├─ Check: "AML" ∈ field_to_enums["disease"]? ✓
    │   ├─ Check: "age_at_censor_status" ∈ all_fields? ✓
    │   ├─ Check: 1825 is numeric? ✓
    │   ├─ Check: "stagings" is a valid nested path? ✓
    │   ├─ Check: "disease_phase" ∈ all_fields? ✓ (special case)
    │   └─ is_valid=True, fields_used=["disease", "age_at_censor_status", "disease_phase"]
    │
    ├─[Route] → explain_filter
    │
    ├─[Node 7] explain_filter
    │   └─ OpenAI call(filter JSON) → "Matches AML subjects under 5 years old at Initial Diagnosis"
    │
    └─ LangGraph returns final_state

FastAPI reads final_state:
    ├─ SSE: token {"text": "Matches AML subjects under 5 years old..."}
    ├─ SSE: filter_json {"filter": {...}, "is_valid": true, "errors": [], "fields_used": [...]}
    └─ SSE: done {"conversation_id": "abc123"}

Frontend (useChat hook):
    ├─ token event  → message.content = "Matches AML subjects..."
    ├─ filter_json  → message.filter = FilterResult (renders FilterDisplay)
    └─ done         → isLoading=false

User sees:
    ┌─────────────────────────────────────────────────┐
    │ Matches AML subjects under 5 years old at       │
    │ Initial Diagnosis.                              │
    │                                                 │
    │ ✓ Valid Filter         [Copy]                   │
    │ ┌─────────────────────────────────────────────┐ │
    │ │ {"AND": [                                   │ │
    │ │   {"IN": {"disease": ["AML"]}},             │ │
    │ │   {"LTE": {"age_at_censor_status": 1825}},  │ │
    │ │   ...                                       │ │
    │ │ ]}                                          │ │
    │ └─────────────────────────────────────────────┘ │
    │ disease  age_at_censor_status  disease_phase     │
    └─────────────────────────────────────────────────┘
```
