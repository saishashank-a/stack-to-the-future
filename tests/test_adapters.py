"""Framework adapters: each one on a tiny repo that exercises exactly what static analysis misses."""
import json
from pathlib import Path

import jsonschema

from scan import scan

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "skills" / "stack-to-the-future" / "schema" / "scan.schema.json").read_text(encoding="utf-8"))


def repo(tmp_path, files: dict[str, str]) -> dict:
    for path, body in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(body, encoding="utf-8")
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
        ("event_handler", "server action refundOrder", "app/actions.ts"),
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


def test_nextjs_modules_follow_url_segments():
    from cluster import cluster
    result = cluster(scan(ROOT / "fixtures" / "nextjs-app"))
    assert {m["id"]: m["files"] for m in result["modules"]} == {
        "products": ["app/(shop)/products/[id]/page.tsx", "app/(shop)/products/page.tsx"],
        "orders": ["app/api/orders/route.ts"],
        "app": ["app/_drafts/page.tsx", "app/actions.ts", "app/layout.tsx", "app/page.tsx"],
    }  # route groups and api/ are see-through; root files and _private folders stay with the app
    assert result["unassigned"] == []


def test_nextjs_app_beside_other_folders_splits_only_the_app():
    from cluster import module_folders
    assert module_folders(["app/page.tsx", "app/blog/page.tsx", "app/(auth)/login/page.tsx",
                           "lib/db.ts", "components/nav.tsx"]) == ["app/(auth)/login", "app/blog", "app", "components", "lib"]
    assert module_folders(["pkg/app/layout.py", "pkg/core/x.py"]) == ["pkg/app", "pkg/core"]  # only JS/TS layouts count


def test_fastapi_router_mounted_twice_keeps_every_mount(tmp_path):
    result = repo(tmp_path, {
        "app/__init__.py": "",
        "app/deps.py": (
            "from fastapi import HTTPException\n\n"
            "def require_admin():\n"
            "    raise HTTPException(status_code=403, detail='no')\n"
        ),
        "app/items.py": (
            "from fastapi import APIRouter\n\n"
            "router = APIRouter(prefix='/items')\n\n"
            "@router.get('/')\n"
            "def list_items():\n"
            "    return []\n"
        ),
        "app/main.py": (
            "from fastapi import Depends, FastAPI\n"
            "from app import items\n"
            "from app.deps import require_admin\n\n"
            "app = FastAPI()\n"
            "app.include_router(items.router, prefix='/v2', dependencies=[Depends(require_admin)])\n"
            "app.include_router(items.router, prefix='/v1')\n"
        ),
    })
    ep = next(e for e in result["entry_points"] if e["symbol"] == "list_items")
    assert (ep["label"], ep["path"], ep["also_at"]) == ("GET /v1/items/", "/v1/items/", ["/v2/items/"])
    assert ("list_items", "Depends(require_admin)") in {(b["function"], b["test"]) for b in result["permission_branches"]}


def test_nextjs_flags_incomplete_typescript():
    result = scan(ROOT / "fixtures" / "nextjs-app")
    assert {(i["file"], i["kind"], i["line"], i["symbol"]) for i in result["incomplete"]} == {
        ("app/actions.ts", "todo", 9, "cancelOrder"),
        ("app/actions.ts", "not_implemented", 14, "refundOrder"),
        ("app/(shop)/products/page.tsx", "stub", 18, "recommend"),
    }


def test_nextjs_anonymous_callbacks_and_constructors_are_not_stubs(tmp_path):
    result = repo(tmp_path, {
        "package.json": '{"dependencies": {"next": "15.0.0"}}',
        "app/page.tsx": (
            "export default function Home() {\n"
            "  const noop = () => {};\n"
            "  return <button onClick={() => {}}>x</button>;\n"
            "}\n"
            "class Cart {\n  constructor() {}\n}\n"
        ),
    })
    assert [(i["kind"], i["symbol"]) for i in result["incomplete"]] == [("stub", "noop")]
