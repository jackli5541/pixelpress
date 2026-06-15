from typing import Any
from uuid import uuid4


def success_response(data: Any, message: str = "ok") -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "request_id": str(uuid4()),
        "data": data,
    }
