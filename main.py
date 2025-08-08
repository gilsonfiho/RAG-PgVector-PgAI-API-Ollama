from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncpg
import httpx
import os

app = FastAPI()

# Configurações
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/dbname")
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434")

# Conexão com o banco
pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)

@app.on_event("shutdown")
async def shutdown():
    await pool.close()

# Modelos de dados para entrada/saída
class EmbedRequest(BaseModel):
    text: str

class EmbedResponse(BaseModel):
    embedding: List[float]

class Document(BaseModel):
    id: Optional[int]
    content: str
    metadata: Optional[dict]

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

class SearchResult(BaseModel):
    id: int
    content: str
    score: float

class RagQueryRequest(BaseModel):
    query: str

class ChatMessage(BaseModel):
    role: str  # system, user, assistant
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    seed: Optional[int] = None
    temperature: Optional[float] = 0.7

# Função para chamar o Ollama para gerar embedding
async def get_embedding(text: str) -> List[float]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OLLAMA_API_URL}/embed", json={
            "model": "mistral",
            "input": text
        })
        resp.raise_for_status()
        data = resp.json()
        return data["embedding"]  # ajuste conforme a resposta da API Ollama

# Endpoint para gerar embedding e salvar no banco
@app.post("/embed", response_model=EmbedResponse)
async def embed_text(req: EmbedRequest):
    embedding = await get_embedding(req.text)

    # Aqui você pode salvar embedding no banco se quiser
    # await pool.execute("INSERT INTO embeddings (vector) VALUES ($1)", embedding)

    return {"embedding": embedding}

# Endpoint para inserir documento + embedding
@app.post("/documents", response_model=Document)
async def add_document(doc: Document):
    embedding = await get_embedding(doc.content)

    async with pool.acquire() as conn:
        # Salva documento e embedding no banco, assumindo tabelas 'documents' e 'embeddings'
        doc_id = await conn.fetchval(
            "INSERT INTO documents (content, metadata) VALUES ($1, $2) RETURNING id",
            doc.content, doc.metadata
        )
        # Salva vetor no pgVector, assumindo coluna vector em embeddings vinculada a doc_id
        await conn.execute(
            "INSERT INTO embeddings (document_id, vector) VALUES ($1, $2)",
            doc_id, embedding
        )

    doc.id = doc_id
    return doc

# Endpoint para busca vetorial
@app.post("/vectors/search", response_model=List[SearchResult])
async def search_vectors(req: SearchRequest):
    embedding = await get_embedding(req.query)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d.id, d.content, 1 - (e.vector <=> $1) AS score
            FROM embeddings e
            JOIN documents d ON d.id = e.document_id
            ORDER BY e.vector <=> $1
            LIMIT $2
            """,
            embedding, req.top_k
        )

    return [
        SearchResult(id=row["id"], content=row["content"], score=row["score"])
        for row in rows
    ]

# Endpoint RAG: busca + geração com contexto
@app.post("/rag/query")
async def rag_query(req: RagQueryRequest):
    # 1. Busca vetorial para contexto
    embedding = await get_embedding(req.query)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d.content
            FROM embeddings e
            JOIN documents d ON d.id = e.document_id
            ORDER BY e.vector <=> $1
            LIMIT 5
            """,
            embedding
        )

    context_text = "\n\n".join([r["content"] for r in rows])

    prompt = f"Contexto:\n{context_text}\n\nPergunta: {req.query}\nResposta:"

    # 2. Chamada para Ollama para gerar resposta com base no contexto
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OLLAMA_API_URL}/generate", json={
            "model": "mistral",
            "prompt": prompt,
            "temperature": 0.7,
            "max_tokens": 256
        })
        resp.raise_for_status()
        data = resp.json()

    return {"answer": data.get("response")}

# Endpoint para chat completo
@app.post("/chat")
async def chat_complete(req: ChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    payload = {
        "model": req.model,
        "messages": messages,
        "temperature": req.temperature
    }

    if req.seed is not None:
        payload["seed"] = req.seed

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OLLAMA_API_URL}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Ajuste conforme o formato da resposta
    return {"response": data["choices"][0]["message"]["content"]}
