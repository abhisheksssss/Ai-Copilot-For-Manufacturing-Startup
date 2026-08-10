# 🏭 Backend Engine — AI Copilot for Manufacturing Startups

FastAPI + LangGraph + PyTorch/SentenceTransformers backend powering multi-agent manufacturing planning, digital twin financial simulations, and scheme research.

---

## ⚡ Quick Start

### 1. Install Dependencies
Using standard pip:
```bash
pip install -r requirements.txt
```
Or using [uv](https://github.com/astral-sh/uv):
```bash
uv sync
```

### 2. Set Environment Variables
Create a `.env` file in the `backend/` root directory:
```env
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
ALLOWED_ORIGINS=http://localhost:3000,https://*.vercel.app
GEMINI_API_KEY=your_key
GROQ_API_KEY=your_key
OPENROUTER_API_KEY=your_key
```

### 3. Run Server
```bash
uvicorn main:app --reload --port 8000
```
Server running at `http://127.0.0.1:8000`.

- **Swagger Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check Endpoint**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 🏛️ Project Architecture
- `main.py`: FastAPI server routes, streaming SSE endpoints, CORS configuration.
- `agents/`: Multi-agent orchestration, LangGraph state workflows, chatbot loop guardrails.
- `agents/tools/`: Manufacturing BOM, Government MSME/PLI schemes, web scraper, financial planning tools.
- `digital_twin/`: Financial CapEx/OpEx engine, physics bottleneck simulator, 3D scene generator.
- `core/`: Database connections, auth security JWT, settings configurations.
