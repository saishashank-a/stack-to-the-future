"""Framework adapters: each one on a tiny repo that exercises exactly what static analysis misses."""
import json
from pathlib import Path

import jsonschema

from scan import scan

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "skills" / "stack-to-the-future" / "schema" / "scan.schema.json").read_text())


def repo(tmp_path, files: dict[str, str]) -> dict:
    for path, body in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(body)
    result = scan(tmp_path)
    jsonschema.validate(result, SCHEMA)
    return result


def edges(result) -> set:
    return {(f"{c['file']}::{c['caller']}", f"{c['target_file']}::{c['target_symbol']}") for c in result["calls"]}


def test_nextjs_app_router_fixture():
    result = scan(ROOT / "fixtures" / "nextjs-app")
    jsonschema.validate(result, SCHEMA)
    assert {(e["kind"], e["label"], e["file"]) for e in result["entry_points"]} == {
        ("ui_page", "/", "app/page.tsx"),
        ("ui_page", "/products", "app/(shop)/products/page.tsx"),
        ("ui_page", "/products/[id]", "app/(shop)/products/[id]/page.tsx"),
        ("api_route", "GET /api/orders", "app/api/orders/route.ts"),
        ("api_route", "POST /api/orders", "app/api/orders/route.ts"),
        ("event_handler", "server action placeOrder", "app/actions.ts"),
        ("event_handler", "server action cancelOrder", "app/actions.ts"),
    }  # app/_drafts/page.tsx is private: no route
    post = next(e for e in result["entry_points"] if e["label"] == "POST /api/orders")
    assert (post["symbol"], post["start_line"], post["end_line"]) == ("POST", 7, 11)
    hints = {f["path"]: (f["hint"], f.get("group")) for f in result["files"]}
    assert hints["app/layout.tsx"] == ("foundation", "wiring")


def test_nextjs_adapter_ignores_vite_react(tmp_path):
    result = repo(tmp_path, {
        "frontend/package.json": json.dumps({"dependencies": {"react": "19", "vite": "6"}}),
        "frontend/src/app/page.tsx": "export default function Page() { return null }\n",
    })
    assert not result["entry_points"]


def test_celery_send_task_by_name_and_beat_schedule(tmp_path):
    result = repo(tmp_path, {
        "app/__init__.py": "",
        "app/worker.py": (
            "from celery import Celery\n"
            "celery_app = Celery('x')\n"
            "celery_app.conf.update(beat_schedule={\n"
            "    'nightly': {'task': 'app.tasks.rebuild_index', 'schedule': 3600},\n"
            "})\n"
        ),
        "app/tasks.py": (
            "from celery import shared_task\n\n"
            "@shared_task\n"
            "def rebuild_index():\n"
            "    return 1\n"
        ),
        "app/api.py": (
            "from app.worker import celery_app\n\n"
            "def trigger():\n"
            "    celery_app.send_task('app.tasks.rebuild_index')\n"
        ),
    })
    assert ("app/api.py::trigger", "app/tasks.py::rebuild_index") in edges(result)  # default name = module.function
    (beat,) = [e for e in result["entry_points"] if e["kind"] == "scheduled_job"]
    assert (beat["label"], beat["file"], beat["start_line"]) == ("app.tasks.rebuild_index (3600)", "app/worker.py", 4)
    assert ("app/worker.py::<module>", "app/tasks.py::rebuild_index") in edges(result)


def test_sqlalchemy_event_hooks_become_edges(tmp_path):
    result = repo(tmp_path, {
        "shop/__init__.py": "",
        "shop/models.py": (
            "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column\n\n"
            "class Base(DeclarativeBase):\n    pass\n\n"
            "class Order(Base):\n"
            "    __tablename__ = 'orders'\n"
            "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        ),
        "shop/hooks.py": (
            "from sqlalchemy import event\n"
            "from shop.models import Order\n\n"
            "@event.listens_for(Order, 'after_insert')\n"
            "def announce(mapper, connection, target):\n    pass\n\n"
            "def stamp(mapper, connection, target):\n    pass\n\n"
            "event.listen(Order, 'before_update', stamp)\n"
        ),
    })
    assert {("shop/models.py::Order", "shop/hooks.py::announce"), ("shop/models.py::Order", "shop/hooks.py::stamp")} <= edges(result)


def test_fastapi_annotated_deps_nested_prefixes_tasks_and_middleware(tmp_path):
    result = repo(tmp_path, {
        "app/__init__.py": "",
        "app/config.py": "class Settings:\n    API_V1_STR = '/api/v1'\nsettings = Settings()\n",
        "app/deps.py": (
            "from typing import Annotated\n"
            "from fastapi import Depends, HTTPException\n\n"
            "def get_current_user():\n"
            "    raise HTTPException(status_code=403, detail='no')\n\n"
            "def get_superuser(user=Depends(get_current_user)):\n"
            "    return user\n\n"
            "CurrentUser = Annotated[dict, Depends(get_current_user)]\n"
        ),
        "app/mail.py": "def send_welcome(email):\n    pass\n",
        "app/timing.py": (
            "from starlette.middleware.base import BaseHTTPMiddleware\n\n"
            "class Timing(BaseHTTPMiddleware):\n    pass\n"
        ),
        "app/routes/__init__.py": "",
        "app/routes/users.py": (
            "from fastapi import APIRouter, BackgroundTasks, Depends\n"
            "from app.deps import CurrentUser, get_superuser\n"
            "from app.mail import send_welcome\n\n"
            "router = APIRouter(prefix='/users')\n\n"
            "@router.get('/me')\n"
            "def read_me(current_user: CurrentUser):\n"
            "    return current_user\n\n"
            "@router.post('/', dependencies=[Depends(get_superuser)])\n"
            "def create_user(tasks: BackgroundTasks):\n"
            "    tasks.add_task(send_welcome, 'x')\n"
        ),
        "app/api.py": (
            "from fastapi import APIRouter\n"
            "from app.routes import users\n\n"
            "api_router = APIRouter()\n"
            "api_router.include_router(users.router)\n"
        ),
        "app/main.py": (
            "from fastapi import FastAPI\n"
            "from app.api import api_router\n"
            "from app.config import settings\n"
            "from app.timing import Timing\n\n"
            "app = FastAPI()\n"
            "app.add_middleware(Timing)\n"
            "app.include_router(api_router, prefix=settings.API_V1_STR)\n"
        ),
    })
    labels = {e["symbol"]: e["label"] for e in result["entry_points"]}
    assert labels["read_me"] == "GET {API_V1_STR}/users/me"  # non-literal prefix kept as a named placeholder
    assert labels["create_user"] == "POST {API_V1_STR}/users/"
    assert labels["send_welcome"] == "send_welcome"  # BackgroundTasks.add_task target is a job
    assert {("app/routes/users.py::read_me", "app/deps.py::get_current_user"),     # via Annotated alias
            ("app/routes/users.py::create_user", "app/deps.py::get_superuser"),    # via decorator dependencies=
            ("app/deps.py::get_superuser", "app/deps.py::get_current_user"),       # dependency chain
            ("app/routes/users.py::create_user", "app/mail.py::send_welcome")} <= edges(result)
    guarded = {(b["function"], b["test"]) for b in result["permission_branches"]}
    # The alias is expanded: the fact names the real dependency behind `current_user: CurrentUser`.
    assert {("read_me", "Depends(get_current_user)"), ("create_user", "Depends(get_superuser)")} <= guarded
    hints = {f["path"]: (f["hint"], f.get("group")) for f in result["files"]}
    assert hints["app/timing.py"] == ("foundation", "wiring")
