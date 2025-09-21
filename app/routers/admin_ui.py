from __future__ import annotations

from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from fastui import FastUI, prebuilt_html
from fastui import components as c
from fastui import events as e
def _ensure_fastui_ready() -> None:
    try:
        # Ensure Pydantic and component models are fully defined in runtime context
        FastUI.model_rebuild()
        # Rebuild commonly used components first
        for _obj in (getattr(c, n) for n in ("AnyComponent", "Page", "Form", "ModelForm")):
            if hasattr(_obj, "model_rebuild"):
                try:
                    _obj.model_rebuild()
                except Exception:
                    pass
        # Then best-effort rebuild all components
        for _n in dir(c):
            try:
                _obj = getattr(c, _n)
                if hasattr(_obj, 'model_rebuild'):
                    _obj.model_rebuild()
            except Exception:
                pass
    except Exception:
        # Avoid failing the request; FastUI may still work
        pass

from ..auth import require_roles, verify_password, create_access_token
from ..db import get_db
from ..models import User, Task, Subtask, Subject
from ..schemas import StatusResponse, UserCreate, UserUpdate, SubjectCreate
from ..auth import get_password_hash


public_router = APIRouter(prefix="/admin", tags=["admin-ui"])  # no auth
router = APIRouter(prefix="/admin", tags=["admin-ui"], dependencies=[Depends(require_roles("admin"))])


# --- Minimal helpers to emit FastUI JSON without constructing Pydantic models ---
def ui_heading(text: str, level: int = 2) -> dict:
    return {"type": "Heading", "text": text, "level": level}


def ui_text(text: str) -> dict:
    return {"type": "Text", "text": text}


def ui_button(text: str, goto_url: str) -> dict:
    return {"type": "Button", "text": text, "onClick": {"type": "go-to", "url": goto_url}}


def ui_div(children: list[dict]) -> dict:
    return {"type": "Div", "components": children}


def ui_page(children: list[dict]) -> dict:
    return {"type": "Page", "components": children}


@public_router.get("/", response_class=HTMLResponse)  # public: redirects to /admin/login if no token
async def admin_index() -> str:
    # FastUI prebuilt HTML, initial page will be fetched from below JSON endpoint
    html = prebuilt_html(
        title="Shelper Admin",
        api_root_url="/admin/api/pages",
        api_path_mode="append",
        api_path_strip="/admin",
    )
    # Inject a tiny helper to pass ?token=... once and attach Authorization header to all fetch() calls
    helper = """
<script>
(function(){
  try {
    const usp = new URLSearchParams(window.location.search);
    const tok = usp.get('token');
    if (tok) { localStorage.setItem('admin_bearer_token', tok); }
    const t = localStorage.getItem('admin_bearer_token');
    if (!t) { window.location.replace('/admin/login'); return; }
    const orig = window.fetch.bind(window);
    window.fetch = (input, init) => {
      init = init || {};
      init.headers = init.headers || {};
      if (init.headers instanceof Headers) {
        init.headers.set('Authorization', 'Bearer ' + t);
      } else if (Array.isArray(init.headers)) {
        init.headers.push(['Authorization', 'Bearer ' + t]);
      } else {
        init.headers['Authorization'] = 'Bearer ' + t;
      }
      return orig(input, init);
    };
  } catch (e) { console.warn('admin token helper error', e); }
})();
</script>
"""
    return html + helper


@public_router.get("/login", response_class=HTMLResponse)
async def admin_login_form() -> str:
    return """
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>Admin Login</title>
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <style>
      body{font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:#f7f7f7;}
      .card{max-width:420px;margin:10vh auto;background:#fff;padding:24px;border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,.06)}
      label{display:block;margin:.5rem 0 .25rem;color:#111827;font-weight:600}
      input{width:100%;padding:.75rem;border:1px solid #e5e7eb;border-radius:8px}
      button{margin-top:1rem;width:100%;padding:.75rem;border:0;border-radius:8px;background:#3B82F6;color:#fff;font-weight:700}
      .muted{color:#6b7280;font-size:.9rem}
    </style>
  </head>
  <body>
    <div class=\"card\">
      <h2>Admin Login</h2>
      <form method=\"post\" action=\"/admin/login\"> 
        <label for=\"email\">Email</label>
        <input id=\"email\" name=\"email\" type=\"email\" required />
        <label for=\"password\">Password</label>
        <input id=\"password\" name=\"password\" type=\"password\" required />
        <button type=\"submit\">Login</button>
      </form>
      <p class=\"muted\">Use an admin account to access the dashboard.</p>
    </div>
  </body>
 </html>
"""


@public_router.post("/login", response_class=HTMLResponse)
async def admin_login(email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)) -> str:
    from sqlalchemy import select
    from ..models import User

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return """
<!DOCTYPE html><html><body>
<script>alert('Invalid credentials'); window.location.replace('/admin/login');</script>
</body></html>
"""
    if user.role != "admin":
        return """
<!DOCTYPE html><html><body>
<script>alert('Admin role required'); window.location.replace('/admin/login');</script>
</body></html>
"""
    token = create_access_token(user_id=user.id, role=user.role)
    # Store token and go to /admin
    return f"""
<!DOCTYPE html><html><body>
<script>
  localStorage.setItem('admin_bearer_token', {token!r});
  window.location.replace('/admin');
</script>
</body></html>
"""


@router.get("/api/pages", include_in_schema=False)
async def admin_pages_root() -> list[dict]:
    # Alias to home so that initial request to /admin/api/pages works
    return await admin_home()


@router.get("/api/pages/home", include_in_schema=False)
async def admin_home() -> list[dict]:
    return [
        ui_page([
            ui_heading("Shelper Admin", 2),
            ui_text("Quick links"),
            ui_button("Users", "/admin/users"),
            ui_button("Subjects", "/admin/subjects"),
            ui_button("Tasks", "/admin/tasks"),
        ])
    ]


@router.get("/api/pages/users", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_users(db: AsyncSession = Depends(get_db)) -> List[c.Component]:
    _ensure_fastui_ready()
    result = await db.execute(select(User).order_by(User.id.asc()))
    users = list(result.scalars().all())
    items: List[c.Component] = [c.Heading(text="Users", level=3)]
    if not users:
        items.append(c.Text(text="No users yet."))
    for u in users:
        items.append(
            c.Div(
                components=[
                    c.Text(text=f"#{u.id} • {u.name} • {u.email} • {u.role}"),
                    c.Button(text="Delete", on_click=e.PostEvent(url=f"/admin/api/actions/users/{u.id}/delete")),
                ]
            )
        )
    items.append(c.Button(text="Back", on_click=e.GoToEvent(url="/admin")))
    return [c.Page(components=items)]


@router.post("/api/actions/users/{user_id}/delete", response_model=StatusResponse)
async def admin_user_delete(user_id: int, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    # Do not allow deleting yourself (admin)
    # In practice, we'd get current_user and block if ids match
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return StatusResponse(status="deleted")


@router.get("/api/pages/tasks", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_tasks(db: AsyncSession = Depends(get_db)) -> List[c.Component]:
    _ensure_fastui_ready()
    result = await db.execute(select(Task).order_by(Task.id.desc()))
    tasks = list(result.scalars().unique().all())
    items: List[c.Component] = [c.Heading(text="Tasks", level=3)]
    if not tasks:
        items.append(c.Text(text="No tasks yet."))
    for t in tasks:
        subtasks_count = len(t.subtasks) if hasattr(t, "subtasks") and t.subtasks is not None else 0
        items.append(
            c.Div(
                components=[
                    c.Text(text=f"#{t.id} • child={t.child_id} • subject={t.subject_id} • {t.date} • {t.title or ''} • {t.status} • subtasks={subtasks_count}"),
                    c.Button(text="Delete", on_click=e.PostEvent(url=f"/admin/api/actions/tasks/{t.id}/delete")),
                ]
            )
        )
    items.append(c.Button(text="Back", on_click=e.GoToEvent(url="/admin")))
    return [c.Page(components=items)]


@router.post("/api/actions/tasks/{task_id}/delete", response_model=StatusResponse)
async def admin_task_delete(task_id: int, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    task = await db.get(Task, task_id)
    if task is None:
        return StatusResponse(status="not_found")
    await db.delete(task)
    await db.commit()
    return StatusResponse(status="deleted")


# Users create/edit pages
@router.get("/api/pages/users/new", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_user_new() -> List[c.Component]:
    _ensure_fastui_ready()
    return [
        c.Page(components=[
            c.Heading(text="New User", level=3),
            c.ModelForm(model=UserCreate, submit_url="/admin/api/actions/users/create"),
            c.Button(text="Back", on_click=e.GoToEvent(url="/admin/users")),
        ])
    ]


@router.post("/api/actions/users/create", response_model=StatusResponse)
async def admin_user_create(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    if payload.role not in ("child", "parent", "admin"):
        return StatusResponse(status="invalid_role")
    u = User(name=payload.name, email=str(payload.email), password_hash=get_password_hash(payload.password), role=payload.role)
    db.add(u)
    await db.commit()
    return StatusResponse(status="created")


@router.get("/api/pages/users/{user_id}/edit", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_user_edit(user_id: int, db: AsyncSession = Depends(get_db)) -> List[c.Component]:
    _ensure_fastui_ready()
    u = await db.get(User, user_id)
    if not u:
        return [c.Page(components=[c.Text(text="User not found"), c.Button(text="Back", on_click=e.GoToEvent(url="/admin/users"))])]
    return [
        c.Page(components=[
            c.Heading(text=f"Edit User #{u.id}", level=3),
            c.ModelForm(model=UserUpdate, submit_url=f"/admin/api/actions/users/{u.id}/update", initial={
                "name": u.name,
                "email": u.email,
                "role": u.role,
            }),
            c.Button(text="Back", on_click=e.GoToEvent(url="/admin/users")),
        ])
    ]


@router.post("/api/actions/users/{user_id}/update", response_model=StatusResponse)
async def admin_user_update(user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    u = await db.get(User, user_id)
    if not u:
        return StatusResponse(status="not_found")
    if payload.name is not None:
        u.name = payload.name
    if payload.email is not None:
        u.email = str(payload.email)
    if payload.role is not None:
        if payload.role not in ("child", "parent", "admin"):
            return StatusResponse(status="invalid_role")
        u.role = payload.role
    if payload.password is not None:
        u.password_hash = get_password_hash(payload.password)
    await db.commit()
    return StatusResponse(status="updated")


# Tasks: simple create + add-subtask
@router.get("/api/pages/tasks/new", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_task_new() -> List[c.Component]:
    _ensure_fastui_ready()
    return [
        c.Page(components=[
            c.Heading(text="New Task", level=3),
            c.Form(
                submit_url="/admin/api/actions/tasks/admin_create",
                form_fields=[
                    c.FormFieldInput(name="child_id", title="Child ID", input_type="number"),
                    c.FormFieldInput(name="subject_id", title="Subject ID", input_type="number"),
                    c.FormFieldInput(name="date", title="Date (YYYY-MM-DD)", input_type="text"),
                    c.FormFieldInput(name="title", title="Title", input_type="text"),
                ],
            ),
            c.Button(text="Back", on_click=e.GoToEvent(url="/admin/tasks")),
        ])
    ]


@router.post("/api/actions/tasks/admin_create", response_model=StatusResponse)
async def admin_task_create(payload: dict, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    try:
        child_id = int(payload.get("child_id"))
        subject_id = int(payload.get("subject_id"))
    except Exception:
        return StatusResponse(status="invalid_ids")
    date = (payload.get("date") or "").strip() or datetime.utcnow().strftime("%Y-%m-%d")
    title = (payload.get("title") or None)
    t = Task(child_id=child_id, subject_id=subject_id, date=date, title=title, status="todo")
    db.add(t)
    await db.commit()
    return StatusResponse(status="created")


@router.get("/api/pages/tasks/{task_id}/subtasks/new", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_subtask_new(task_id: int) -> List[c.Component]:
    _ensure_fastui_ready()
    return [
        c.Page(components=[
            c.Heading(text=f"Add Subtask to Task #{task_id}", level=3),
            c.Form(submit_url=f"/admin/api/actions/tasks/{task_id}/subtasks/create", form_fields=[
                c.FormFieldInput(name="title", title="Title", input_type="text")
            ]),
            c.Button(text="Back", on_click=e.GoToEvent(url="/admin/tasks")),
        ])
    ]


@router.post("/api/actions/tasks/{task_id}/subtasks/create", response_model=StatusResponse)
async def admin_subtask_create(task_id: int, payload: dict, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    title = (payload.get("title") or "").strip()
    if not title:
        return StatusResponse(status="title_required")
    st = Subtask(task_id=task_id, title=title, status="todo")
    db.add(st)
    await db.commit()
    return StatusResponse(status="created")


# Subjects list/create/edit
@router.get("/api/pages/subjects", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_subjects(db: AsyncSession = Depends(get_db)) -> List[c.Component]:
    _ensure_fastui_ready()
    result = await db.execute(select(Subject).order_by(Subject.id.asc()))
    subs = list(result.scalars().all())
    items: List[c.Component] = [c.Heading(text="Subjects", level=3)]
    items.append(c.Button(text="+ New Subject", on_click=e.GoToEvent(url="/admin/subjects/new")))
    if not subs:
        items.append(c.Text(text="No subjects."))
    for s in subs:
        items.append(c.Div(components=[
            c.Text(text=f"#{s.id} • {s.name}"),
            c.Button(text="Edit", on_click=e.GoToEvent(url=f"/admin/subjects/{s.id}/edit")),
        ]))
    items.append(c.Button(text="Back", on_click=e.GoToEvent(url="/admin")))
    return [c.Page(components=items)]


@router.get("/api/pages/subjects/new", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_subject_new() -> List[c.Component]:
    _ensure_fastui_ready()
    return [
        c.Page(components=[
            c.Heading(text="New Subject", level=3),
            c.ModelForm(model=SubjectCreate, submit_url="/admin/api/actions/subjects/create"),
            c.Button(text="Back", on_click=e.GoToEvent(url="/admin/subjects")),
        ])
    ]


@router.post("/api/actions/subjects/create", response_model=StatusResponse)
async def admin_subject_create(payload: SubjectCreate, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    s = Subject(name=payload.name.strip())
    db.add(s)
    await db.commit()
    return StatusResponse(status="created")


@router.get("/api/pages/subjects/{subject_id}/edit", response_model=FastUI, response_model_exclude_none=True, include_in_schema=False)
async def admin_subject_edit(subject_id: int, db: AsyncSession = Depends(get_db)) -> List[c.Component]:
    _ensure_fastui_ready()
    s = await db.get(Subject, subject_id)
    if not s:
        return [c.Page(components=[c.Text(text="Subject not found"), c.Button(text="Back", on_click=e.GoToEvent(url="/admin/subjects"))])]
    return [
        c.Page(components=[
            c.Heading(text=f"Edit Subject #{s.id}", level=3),
            c.Form(
                submit_url=f"/admin/api/actions/subjects/{s.id}/update",
                form_fields=[c.FormFieldInput(name="name", title="Name", input_type="text")],
                initial={"name": s.name},
            ),
            c.Button(text="Back", on_click=e.GoToEvent(url="/admin/subjects")),
        ])
    ]


@router.post("/api/actions/subjects/{subject_id}/update", response_model=StatusResponse)
async def admin_subject_update(subject_id: int, payload: dict, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    s = await db.get(Subject, subject_id)
    if not s:
        return StatusResponse(status="not_found")
    name = (payload.get("name") or "").strip()
    if not name:
        return StatusResponse(status="name_required")
    s.name = name
    await db.commit()
    return StatusResponse(status="updated")
