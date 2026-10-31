from fastapi import FastAPI

app = FastAPI(
    title="OpsPilot API",
    description="AI-powered procurement and operations copilot",
    version="0.1.0",
)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Check whether the API is running."""
    return {
        "status": "ok",
        "service": "opspilot-api",
    }