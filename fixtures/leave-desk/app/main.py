"""Leave Desk web app."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine
from app.leave.routes import router as leave_router
from app.reports.routes import router as reports_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Leave Desk", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])
app.include_router(leave_router)
app.include_router(reports_router)
