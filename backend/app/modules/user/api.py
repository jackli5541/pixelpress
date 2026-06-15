from fastapi import APIRouter

from app.common.responses import success_response

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def get_current_user() -> dict:
    return success_response(
        {
            "authenticated": False,
            "role": "guest",
        }
    )
