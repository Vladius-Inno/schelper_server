from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable

import httpx
import flet as ft
import flet.fastapi
from fastapi import FastAPI


class ApiClient:
    def __init__(self, fastapi_app: FastAPI):
        self.fastapi_app = fastapi_app
        self.token: str | None = None

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        async with httpx.AsyncClient(app=self.fastapi_app, base_url="http://admin") as client:
            response = await client.request(method, path, headers=headers, **kwargs)
        response.raise_for_status()
        return response

    async def json(self, method: str, path: str, **kwargs) -> Any:
        resp = await self.request(method, path, **kwargs)
        if resp.content:
            return resp.json()
        return None


def create_admin_app(fastapi_app: FastAPI):
    def main(page: ft.Page):
        api = ApiClient(fastapi_app)

        page.title = "Shelper Admin"
        page.horizontal_alignment = ft.CrossAxisAlignment.START
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.padding = 20
        page.scroll = ft.ScrollMode.ADAPTIVE

        status_text = ft.Text()

        def run_async(func: Callable[..., Awaitable[Any]], *args, **kwargs) -> None:
            async def runner() -> None:
                await func(*args, **kwargs)

            page.run_task(runner)

        def set_status(message: str, is_error: bool = False):
            status_text.value = message
            status_text.color = ft.Colors.RED if is_error else ft.Colors.GREEN
            page.update()

        def format_timestamp(value: str | None) -> str:
            if not value:
                return "-"
            normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
            try:
                dt = datetime.fromisoformat(normalized)
                return dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                return value

        def user_controls(rows: list[ft.Control] | None = None, error_message: str | None = None) -> list[ft.Control]:
            controls: list[ft.Control] = [
                ft.Text("Create User", weight=ft.FontWeight.BOLD),
                ft.Row(
                    [
                        user_name,
                        user_email,
                        user_password,
                        user_role,
                        ft.ElevatedButton("Create", icon=ft.Icons.ADD, on_click=create_user),
                    ],
                    wrap=True,
                    spacing=12,
                ),
                ft.Divider(),
                ft.Text("Existing Users", weight=ft.FontWeight.BOLD),
            ]
            if error_message:
                controls.append(ft.Text(error_message, color=ft.Colors.ERROR))
            else:
                controls.append(ft.Column(rows, spacing=8) if rows else ft.Text("No users found."))
            return controls

        def subject_controls(items: list[ft.Control] | None = None, error_message: str | None = None) -> list[ft.Control]:
            controls: list[ft.Control] = [
                ft.Row(
                    [subject_name_field, ft.ElevatedButton("Add", icon=ft.Icons.ADD, on_click=lambda e: run_async(create_subject))],
                    spacing=12,
                ),
                ft.Divider(),
            ]
            if error_message:
                controls.append(ft.Text(error_message, color=ft.Colors.ERROR))
            else:
                controls.append(ft.Column(items, spacing=8) if items else ft.Text("No subjects yet."))
            return controls

        def task_controls(items: list[ft.Control] | None = None, error_message: str | None = None) -> list[ft.Control]:
            controls: list[ft.Control] = [
                ft.Text("Create Task", weight=ft.FontWeight.BOLD),
                ft.Row(
                    [
                        task_child_field,
                        task_subject_field,
                        task_date_field,
                        task_title_field,
                        ft.ElevatedButton("Create", icon=ft.Icons.ADD, on_click=lambda e: run_async(create_task)),
                    ],
                    spacing=12,
                    wrap=True,
                ),
                ft.Divider(),
            ]
            if error_message:
                controls.append(ft.Text(error_message, color=ft.Colors.ERROR))
            else:
                controls.append(ft.Column(items, spacing=8) if items else ft.Text("No tasks yet."))
            return controls

        # Containers for data
        users_section = ft.Column(spacing=10)
        subjects_section = ft.Column(spacing=10)
        tasks_section = ft.Column(spacing=10)

        # Login controls
        email_field = ft.TextField(label="Admin Email", autofocus=True, width=280)
        password_field = ft.TextField(label="Password", password=True, can_reveal_password=True, width=280)

        def show_login() -> None:
            page.controls.clear()
            page.add(
                ft.Column(
                    [
                        ft.Text("Shelper Admin", size=26, weight=ft.FontWeight.BOLD),
                        ft.Text("Sign in with an admin account to manage data."),
                        email_field,
                        password_field,
                        ft.ElevatedButton("Login", icon=ft.Icons.LOGIN, on_click=login_click),
                        status_text,
                    ],
                    spacing=12,
                )
            )
            page.update()

        def show_dashboard() -> None:
            users_tab = ft.Tab(text="Users", content=ft.Column([users_section], spacing=12))
            subjects_tab = ft.Tab(text="Subjects", content=ft.Column([subjects_section], spacing=12))
            tasks_tab = ft.Tab(text="Tasks", content=ft.Column([tasks_section], spacing=12))
            tabs = ft.Tabs(tabs=[users_tab, subjects_tab, tasks_tab], expand=True)
            page.controls.clear()
            page.add(ft.Column([tabs, status_text], spacing=16))
            page.update()
            run_async(refresh_all)

        async def refresh_all():
            await asyncio.gather(load_users(), load_subjects(), load_tasks())

        # -------- Users --------
        user_name = ft.TextField(label="Name", width=220)
        user_email = ft.TextField(label="Email", width=220)
        user_password = ft.TextField(label="Password", password=True, can_reveal_password=True, width=220)
        user_role = ft.Dropdown(
            label="Role",
            options=[ft.dropdown.Option("child"), ft.dropdown.Option("parent"), ft.dropdown.Option("admin")],
            value="child",
            width=160,
        )

        async def load_users():
            users_section.controls = [ft.Row([ft.ProgressRing()], alignment=ft.MainAxisAlignment.CENTER)]
            page.update()
            try:
                data = await api.json("GET", "/users/") or []
            except httpx.HTTPStatusError as exc:
                users_section.controls = user_controls(error_message="Unable to load users.")
                page.update()
                set_status(f"Failed to load users: {exc.response.text}", True)
                return
            rows: list[ft.Control] = []
            for user in data:
                rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(f"#{user['id']} - {user['name']}", weight=ft.FontWeight.BOLD),
                                        ft.Text(user["email"]),
                                        ft.Text(f"Role: {user['role']}", size=12, color=ft.Colors.BLUE_GREY),
                                    ],
                                    spacing=4,
                                ),
                                ft.Row(
                                    [
                                        ft.IconButton(
                                            icon=ft.Icons.EDIT,
                                            tooltip="Edit",
                                            on_click=lambda e, u=user: open_user_editor(u),
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE,
                                            tooltip="Delete",
                                            on_click=lambda e, u=user: run_async(delete_user, u["id"])
                                        ),
                                    ]
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        bgcolor=ft.Colors.SECONDARY_CONTAINER,
                        padding=12,
                        border_radius=ft.border_radius.all(8),
                    )
                )
            users_section.controls = user_controls(rows=rows)
            page.update()

        async def create_user_task():
            payload = {
                "name": user_name.value.strip(),
                "email": user_email.value.strip(),
                "password": user_password.value,
                "role": user_role.value,
            }
            if not all([payload["name"], payload["email"], payload["password"], payload["role"]]):
                set_status("Fill all user fields.", True)
                return
            try:
                await api.json("POST", "/auth/register", json=payload)           
                set_status("User created.")
                user_name.value = ""
                user_email.value = ""
                user_password.value = ""
                user_role.value = "child"
                page.update()
                await load_users()
            except httpx.HTTPStatusError as exc:
                set_status(f"Create user failed: {exc.response.text}", True)

        def create_user(e):
            run_async(create_user_task)

        async def delete_user(user_id: int):
            try:
                await api.request("DELETE", f"/users/{user_id}")
                set_status("User deleted.")
                await load_users()
            except httpx.HTTPStatusError as exc:
                set_status(f"Delete failed: {exc.response.text}", True)

        def open_user_editor(user: dict):
            name_field = ft.TextField(label="Name", value=user["name"], width=250)
            email_field = ft.TextField(label="Email", value=user["email"], width=250)
            role_field = ft.Dropdown(
                label="Role",
                value=user["role"],
                options=[ft.dropdown.Option("child"), ft.dropdown.Option("parent"), ft.dropdown.Option("admin")],
                width=200,
            )
            password_field = ft.TextField(label="New password (optional)", password=True, can_reveal_password=True, width=250)

            def close_dialog(*_):
                page.dialog.open = False
                page.update()

            async def submit():
                payload: dict[str, Any] = {}
                if name_field.value.strip() and name_field.value != user["name"]:
                    payload["name"] = name_field.value.strip()
                if email_field.value.strip() and email_field.value != user["email"]:
                    payload["email"] = email_field.value.strip()
                if role_field.value and role_field.value != user["role"]:
                    payload["role"] = role_field.value
                if password_field.value:
                    payload["password"] = password_field.value
                if not payload:
                    close_dialog()
                    return
                try:
                    await api.json("PUT", f"/users/{user['id']}", json=payload)
                    set_status("User updated.")
                    close_dialog()
                    await load_users()
                except httpx.HTTPStatusError as exc:
                    set_status(f"Update failed: {exc.response.text}", True)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Edit User #{user['id']}"),
                content=ft.Column([name_field, email_field, role_field, password_field], tight=True, spacing=12),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: close_dialog()),
                    ft.ElevatedButton("Save", on_click=lambda e: run_async(submit)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.dialog = dialog
            dialog.open = True
            page.update()

        # -------- Subjects --------
        subject_name_field = ft.TextField(label="Subject name", width=260)

        async def load_subjects():
            subjects_section.controls = subject_controls(error_message="Loading subjects...")
            page.update()
            try:
                data = await api.json("GET", "/subjects/") or []
            except httpx.HTTPStatusError as exc:
                subjects_section.controls = subject_controls(error_message="Unable to load subjects.")
                page.update()
                set_status(f"Failed to load subjects: {exc.response.text}", True)
                return
            items: list[ft.Control] = []
            for subject in data:
                items.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(f"#{subject['id']} - {subject['name']}", weight=ft.FontWeight.BOLD),
                                ft.Row(
                                    [
                                        ft.IconButton(
                                            ft.Icons.EDIT,
                                            tooltip="Rename",
                                            on_click=lambda e, s=subject: open_subject_editor(s),
                                        ),
                                        ft.IconButton(
                                            ft.Icons.DELETE,
                                            tooltip="Delete",
                                            on_click=lambda e, s=subject: run_async(delete_subject, s['id']),
                                        ),
                                    ]
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        bgcolor=ft.Colors.SECONDARY_CONTAINER,
                        padding=12,
                        border_radius=8,
                    )
                )
            subjects_section.controls = subject_controls(items=items)
            page.update()

        async def create_subject():
            name = subject_name_field.value.strip()
            if not name:
                set_status("Subject name required", True)
                return
            try:
                await api.request("POST", "/subjects/", json={"name": name})
                subject_name_field.value = ""
                page.update()
                set_status("Subject created.")
                await load_subjects()
            except httpx.HTTPStatusError as exc:
                set_status(f"Create subject failed: {exc.response.text}", True)

        async def delete_subject(subject_id: int):
            try:
                await api.json("DELETE", f"/subjects/{subject_id}")
                set_status("Subject deleted.")
                await load_subjects()
            except httpx.HTTPStatusError as exc:
                set_status(f"Delete subject failed: {exc.response.text}", True)

        def open_subject_editor(subject: dict):
            name_field = ft.TextField(label="Name", value=subject["name"], width=260)

            def close_dialog(*_):
                page.dialog.open = False
                page.update()

            async def submit():
                new_name = name_field.value.strip()
                if not new_name:
                    set_status("Name required", True)
                    return
                try:
                    await api.json("PUT", f"/subjects/{subject['id']}", json={"name": new_name})
                    set_status("Subject updated.")
                    close_dialog()
                    await load_subjects()
                except httpx.HTTPStatusError as exc:
                    set_status(f"Update subject failed: {exc.response.text}", True)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Edit Subject #{subject['id']}"),
                content=name_field,
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: close_dialog()),
                    ft.ElevatedButton("Save", on_click=lambda e: run_async(submit)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.dialog = dialog
            dialog.open = True
            page.update()

        # -------- Tasks --------
        task_child_field = ft.TextField(label="Child ID", width=120)
        task_subject_field = ft.TextField(label="Subject ID", width=120)
        task_date_field = ft.TextField(label="Date (YYYY-MM-DD)", width=160)
        task_title_field = ft.TextField(label="Title", width=240)

        async def load_tasks():
            tasks_section.controls = task_controls(error_message="Loading tasks...")
            tasks_section.update()
            try:
                data = await api.json("GET", "/tasks/") or []
            except httpx.HTTPStatusError as exc:
                tasks_section.controls = task_controls(error_message="Unable to load tasks.")
                tasks_section.update()
                set_status(f"Failed to load tasks: {exc.response.text}", True)
                return
            controls: list[ft.Control] = []
            for task in data:
                subtasks_controls: list[ft.Control] = []
                for st in task.get("subtasks", []):
                    subtasks_controls.append(
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Text(f"#{st['id']} - {st['title']} ({st['status']})"),
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                ft.Icons.CHECK_CIRCLE,
                                                tooltip="Mark done",
                                                on_click=lambda e, sid=st["id"]: run_async(set_subtask_status, sid, "done"),
                                            ),
                                            ft.IconButton(
                                                ft.Icons.VERIFIED,
                                                tooltip="Mark checked",
                                                on_click=lambda e, sid=st["id"]: run_async(set_subtask_status, sid, "checked"),
                                            ),
                                            ft.IconButton(
                                                ft.Icons.DELETE,
                                                tooltip="Delete",
                                                on_click=lambda e, sid=st["id"]: run_async(delete_subtask, sid),
                                            ),
                                        ]
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            bgcolor=ft.Colors.TERTIARY_CONTAINER,
                            padding=8,
                            border_radius=6,
                        )
                    )
                header_row = ft.Row(
                    [
                        ft.Text(f"Task #{task['id']} - child {task['child_id']} subject {task['subject_id']}", weight=ft.FontWeight.BOLD),
                        ft.Text(task.get("title") or "", color=ft.Colors.BLUE_GREY),
                        ft.Text(task.get("status", ""), color=ft.Colors.GREEN),
                        ft.IconButton(ft.Icons.DELETE, tooltip="Delete task", on_click=lambda e, tid=task["id"]: run_async(delete_task, tid)),
                        ft.IconButton(ft.Icons.ADD, tooltip="Add subtask", on_click=lambda e, tid=task["id"]: open_subtask_dialog(tid)),
                    ],
                    spacing=12,
                    wrap=True,
                )
                meta_row = ft.Row(
                    [
                        ft.Text(f"Date: {task.get('date', '-')}", size=12, color=ft.Colors.BLUE_GREY),
                        ft.Text(f"Created: {format_timestamp(task.get('created_at'))}", size=12, color=ft.Colors.BLUE_GREY),
                        ft.Text(f"Updated: {format_timestamp(task.get('updated_at'))}", size=12, color=ft.Colors.BLUE_GREY),
                    ],
                    spacing=12,
                    wrap=True,
                )
                controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                header_row,
                                meta_row,
                                ft.Column(subtasks_controls, spacing=6) if subtasks_controls else ft.Text("No subtasks."),
                            ],
                            spacing=8,
                        ),
                        bgcolor=ft.Colors.SECONDARY_CONTAINER,
                        padding=12,
                        border_radius=8,
                    )
                )
            tasks_section.controls = task_controls(items=controls)
            tasks_section.update()

        async def create_task():
            try:
                payload = {
                    "subject_id": int(task_subject_field.value.strip()),
                    "title": task_title_field.value.strip() or None,
                    "child_id": int(task_child_field.value.strip()),
                }
            except ValueError:
                set_status("Child ID and Subject ID must be integers", True)
                return
            if task_date_field.value.strip():
                payload["date"] = task_date_field.value.strip()
            try:
                # await api.json("POST", "/tasks/", json=payload)
                await api.request("POST", "/tasks/", json=payload)
                set_status("Task created.")
                task_child_field.value = ""
                task_subject_field.value = ""
                task_date_field.value = ""
                task_title_field.value = ""
                page.update()
                await load_tasks()
            except httpx.HTTPStatusError as exc:
                set_status(f"Create task failed: {exc.response.text}", True)

        async def delete_task(task_id: int):
            try:
                await api.json("DELETE", f"/tasks/{task_id}")
                set_status("Task deleted.")
                await load_tasks()
            except httpx.HTTPStatusError as exc:
                set_status(f"Delete task failed: {exc.response.text}", True)

        def open_subtask_dialog(task_id: int):
            title_field = ft.TextField(label="Subtask title", width=260)

            def close_dialog(*_):
                dialog.open = False
                page.update()
                try:
                    page.overlay.remove(dialog)
                except ValueError:
                    pass

            async def submit():
                title = title_field.value.strip()
                if not title:
                    set_status("Title required", True)
                    return
                try:
                    await api.json("POST", f"/tasks/{task_id}/subtasks", json={"title": title})
                    set_status("Subtask added.")
                    close_dialog()
                    await load_tasks()
                except httpx.HTTPStatusError as exc:
                    set_status(f"Add subtask failed: {exc.response.text}", True)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"New subtask for task {task_id}"),
                content=title_field,
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: close_dialog()),
                    ft.ElevatedButton("Add", on_click=lambda e: run_async(submit)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            if dialog not in page.overlay:
                page.overlay.append(dialog)
            dialog.open = True
            page.update()

        async def set_subtask_status(subtask_id: int, status: str):
            try:
                await api.json("PATCH", f"/tasks/subtasks/{subtask_id}", json={"status": status})
                set_status(f"Subtask updated to {status}.")
                await load_tasks()
            except httpx.HTTPStatusError as exc:
                set_status(f"Update subtask failed: {exc.response.text}", True)

        async def delete_subtask(subtask_id: int):
            try:
                await api.json("DELETE", f"/tasks/subtasks/{subtask_id}")
                set_status("Subtask deleted.")
                await load_tasks()
            except httpx.HTTPStatusError as exc:
                set_status(f"Delete subtask failed: {exc.response.text}", True)

        # -------- Authentication --------
        async def login_task():
            email = email_field.value.strip()
            password = password_field.value
            if not email or not password:
                set_status("Email and password required", True)
                return
            try:
                data = await api.json("POST", "/auth/login", json={"email": email, "password": password})
            except httpx.HTTPStatusError as exc:
                set_status(f"Login failed: {exc.response.text}", True)
                return
            api.token = data.get("token")
            if not api.token:
                set_status("Login response missing token", True)
                return
            page.session.set("admin_token", api.token)
            set_status("Logged in.")
            show_dashboard()

        def login_click(e):
            run_async(login_task)

        # Auto login if token in session
        saved_token = page.session.get("admin_token")
        if saved_token:
            api.token = saved_token
            show_dashboard()
        else:
            show_login()

    return flet.fastapi.app(main)
