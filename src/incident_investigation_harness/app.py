from fastapi import FastAPI

app = FastAPI(title="Incident Investigation Harness")


@app.get("/health", status_code=200)
def health() -> dict[str, str]:
    """Report that the harness service is ready."""
    return {"status": "ok"}
