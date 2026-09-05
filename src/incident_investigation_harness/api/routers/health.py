from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", status_code=200)
def health() -> dict[str, str]:
    """Report that the harness service is ready."""
    return {"status": "ok"}
