from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import ApplicationError, DatabaseNotConfiguredError
from app.core.responses import error_response, success_response
from app.db.session import get_engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Do not connect to Neon or alter schema during application startup."""
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(_: Request, error: ApplicationError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content=error_response(error.message))

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _: Request, __: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content=error_response("Request validation failed"))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, error: HTTPException) -> JSONResponse:
        message = error.detail if isinstance(error.detail, str) else "Request failed"
        return JSONResponse(status_code=error.status_code, content=error_response(message))

    @app.exception_handler(DatabaseNotConfiguredError)
    async def database_not_configured_handler(
        _: Request, __: DatabaseNotConfiguredError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_response("Database is not configured"),
        )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, object]:
        return success_response("Application is healthy", {"status": "ok"})

    @app.get("/health/database", tags=["health"])
    def database_health() -> JSONResponse:
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
                schema_exists = connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name = :schema)"
                    ),
                    {"schema": settings.database_schema},
                )
                table_count = connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema = :schema AND table_type = 'BASE TABLE'"
                    ),
                    {"schema": settings.database_schema},
                )
        except DatabaseNotConfiguredError:
            return JSONResponse(
                status_code=503,
                content=error_response("Database is not configured"),
            )
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content=error_response("Database connection is unavailable"),
            )

        if not schema_exists:
            return JSONResponse(
                status_code=503,
                content=error_response("Database schema is unavailable"),
            )

        return JSONResponse(
            content=success_response(
                "Database is healthy",
                {"status": "ok", "schema": settings.database_schema, "table_count": table_count},
            )
        )

    app.include_router(api_router)
    return app


app = create_app()
