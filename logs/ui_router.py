from fastapi import APIRouter, Response
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/")
async def home_route():
    """Serves the main frontend single-page dashboard"""
    return FileResponse("ui/index.html")


@router.get("/favicon.ico", include_in_schema=False)
async def favicon_silencer():
    """Silences browser requests for favicon.ico with 204 No Content"""
    return Response(status_code=204)
