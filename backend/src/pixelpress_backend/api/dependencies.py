from pixelpress_backend.services.layout_service import layout_service
from pixelpress_backend.services.operation_service import operation_service


def get_layout_service():
    return layout_service


def get_operation_service():
    return operation_service
