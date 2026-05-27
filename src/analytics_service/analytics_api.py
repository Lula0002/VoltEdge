"""Analytics Service — Simple health check service"""

from fastapi import APIRouter

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/health")
async def health():
    """Health check for Analytics Service."""
    return {"status": "healthy", "service": "analytics-service"}
