from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """Wrap all errors in a uniform JSON envelope: {"error": {"code", "detail"}}."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    code = getattr(exc, "default_code", "error")

    if isinstance(detail, dict) and "detail" in detail:
        detail = detail["detail"]

    response.data = {"error": {"code": code, "detail": str(detail)}}
    return response