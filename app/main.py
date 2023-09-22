# main.py

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration


class Settings(BaseSettings):
    # App settings
    PROJECT_NAME: str = "FastAPI Sentry Demo"
    API_V1_STR: str = "/api/v1"

    # Debug settings
    IS_DEBUG: bool = False  # Set to True to enable debug mode

    # CORS settings
    BACKEND_CORS_ORIGINS: list = ["http://localhost:8000"]

    # Sentry settings
    SENTRY_DSN: str

    # Pydantic settings config
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def create_app(settings):
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        debug=settings.IS_DEBUG,
    )
    app.settings = settings

    if settings.BACKEND_CORS_ORIGINS:
        # Configure CORS (optional)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(org) for org in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(GZipMiddleware)
    app.add_middleware(TrustedHostMiddleware)
    if settings.IS_DEBUG is False:
        app.add_middleware(HTTPSRedirectMiddleware)

    # Initialize Sentry SDK
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        # integrations=[
        #     StarletteIntegration(transaction_style="endpoint"),
        #     FastApiIntegration(transaction_style="endpoint"),
        # ], # Add the FastAPI integration to Sentry SDK (optional)
        traces_sample_rate=1.0,  # Set to 1.0 to capture all transactions
        release="1.0.0",  # Specify the release version of your application
        environment="production",  # Specify the environment (e.g., production, development)
        send_default_pii=True,  # Send personally identifiable information (PII)
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        profiles_sample_rate=1.0,
    )

    return app


settings = Settings()
app = create_app(settings)


# Custom exception handler for Pydantic validation errors
async def custom_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    error_details = []
    for error in exc.errors():
        loc = ".".join(error["loc"])
        msg = error["msg"]
        type_ = error["type"]
        error_details.append({"loc": loc, "msg": msg, "type": type_})
    response_data = {"detail": error_details[-1]}
    sentry_sdk.capture_exception(exc)  # Capture exception with Sentry SDK
    return JSONResponse(content=response_data, status_code=400)


# Override default exception handlers with custom ones
app.exception_handler(RequestValidationError)(custom_validation_exception_handler)
app.exception_handler(HTTPException)(http_exception_handler)


# Create a custom error handler for HTTPExceptions
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    sentry_sdk.capture_exception(exc)  # Capture the exception with Sentry
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


app.add_exception_handler(HTTPException, custom_http_exception_handler)


@app.get("/", description="This is a test endpoint")
async def root():
    return {"message": "Hello World"}


@app.get("/sentry-debug", description="This is a test endpoint to trigger an error")
async def trigger_error():
    # Example: Add user context
    with sentry_sdk.push_scope() as scope:
        scope.user = {"id": 123, "username": "exampleuser"}

    # Example: Add custom breadcrumb
    sentry_sdk.add_breadcrumb(
        message="User accessed the root endpoint",
        category="user",
        level="info",
    )
    result = 1 / 0  # Simulate a division by zero error

    return {"result": result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
