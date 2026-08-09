from fastapi import FastAPI

app = FastAPI(
    title="HackMatrix API",
    description="FastAPI backend setup with UV package manager",
    version="0.1.0",
)


@app.get("/")
def read_root():
    return {
        "message": "Welcome to HackMatrix API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
