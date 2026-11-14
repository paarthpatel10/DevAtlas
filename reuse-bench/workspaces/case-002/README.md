# Data Assistant

An assistant that answers questions over two kinds of data:

- Analytical questions are turned into SQL by an LLM and run against a PostgreSQL database.
- Document questions are answered with retrieval over uploaded documents.

A LangGraph workflow routes each question to the right pipeline and formats the response.

## Layout

- `app/api` - FastAPI application
- `app/graph` - workflow, nodes and edges
- `app/agents` - router, SQL, document and response agents
- `app/database` - PostgreSQL connection, schema introspection, SQL execution
- `app/rag` - chunking, embeddings, retrieval, generation
- `app/memory` - conversation memory
- `tests` - pytest suite (external services are stubbed)

## Run

```
pip install -r requirements.txt
docker compose up
pytest -q
```
