from typing import Any
from uuid import uuid4

from app.core.request_context import get_request_id


def success_response(data: Any, message: str = "ok") -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "request_id": get_request_id() or str(uuid4()),
        "data": data,
    }
