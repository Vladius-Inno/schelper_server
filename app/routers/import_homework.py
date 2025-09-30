from __future__ import annotations
from rapidfuzz import process
import re

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.routers.tasks import create_task, make_task_hash, get_task_by_hash, get_task_by_subject_date
from app.service.agent_parser import agent_parse_homework

from ..auth import get_current_user
from ..db import get_db
from ..models import User, Task, Subtask, TASK_STATUS_VALUES
from ..schemas import HomeworkImportRequest, TaskCreate, TaskUpdate, TaskOut, SubtaskCreate, SubtaskUpdate, SubtaskOut, StatusResponse
from app.routers.subjects import get_subject_id_by_name


router = APIRouter(prefix="/import", tags=["import"])


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def _tomorrow_str() -> str:
    return (datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

def has_homework(subject: dict) -> bool:
    subtasks = subject["task"]["subtasks"]
    if len(subtasks) != 1:
        return True
    
    text = subtasks[0]["detail"].lower()
    phrases = ["домашнего задания нет", "нет домашнего задания", "дз нет", "домашки нет"]
    
    return not any(phrase in text for phrase in phrases)

def trim_description(text: str) -> str:
    return text if len(text) <= 50 else text[:50].rstrip() + "..."

# ------------------ SUBJECTS ------------------
SUBJECTS = {
    "математика": ["мат", "мат-ка", "матеша", "мат.", "матем"],
    "русский язык": ["рус", "русский", "рус. яз.", "руский"],
    "английский язык": ["англ", "английский", "англ. яз.", "инглиш"],
    "история": ["ист", "история", "истор"],
    "труд": ["труд", "труды", "технология"],
    "ИЗО": ["изоша", "изобразительное искусство"],
    "биология": ["био", "биол"],
}

def normalize_subject(name: str, threshold: int = 70) -> str:
    """Возвращает каноническое название предмета"""
    name = name.lower().strip()
    name = re.sub(r"[^\w\s]", "", name)

    # 1. Прямое совпадение по словарю
    for canon, variants in SUBJECTS.items():
        if name == canon or name in variants:
            return canon

    # 2. Fuzzy matching
    match, score, _ = process.extractOne(name, SUBJECTS.keys())
    if score >= threshold:
        return match

    # 3. Если ничего не нашли — возвращаем как есть
    return name

# ------------------ CATEGORIES ------------------
CATEGORIES = {
    "exercise": ["пример", "упр", "задача", "решить", "номер", "#", "№", "выполнить", "написать"],
    "theory": ["выучить", "повторить", "прочитать", "пересказ", "учить"],
    "dictation": ["диктант", "словарь"],
    "map": ["карта", "атлас", "контурная карта"],
    "drawing": ["чертеж", "рисунок"],
    "reminder": ["принести", "взять с собой"],
    "file": ["см файл", "выполнить задание в файле", "файл"],
}

def detect_category(text: str, threshold: int = 80) -> str:
    """Возвращает категорию по тексту"""
    text = text.lower().strip()

    # 1. Поиск по ключевым словам
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                return cat

    # 2. Fuzzy поиск по всем ключевым словам
    all_keywords = {kw: cat for cat, kws in CATEGORIES.items() for kw in kws}
    match, score, _ = process.extractOne(text, all_keywords.keys())
    if score >= threshold:
        return all_keywords[match]

    # 3. Если ничего не нашли
    return "other"


@router.post("/homework", response_model=list[TaskOut])
async def import_homework(
    payload: HomeworkImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Принимает текст/файл/скриншот, вызывает ИИ-агента,
    создаёт Task + Subtasks.
    """
    # 1. получить текст
    if payload.text:
        raw_text = payload.text
    # elif payload.file_id:
    #     raw_text = await extract_text_from_file(payload.file_id)
    else:
        raise HTTPException(status_code=400, detail="No homework content provided")

    # 2. вызвать ИИ-агента
    ai_results = await agent_parse_homework(raw_text)
    
    # 3. собрать несколько TaskCreate и сохранить
    # tasks = []
    results = []
    for result in ai_results["subjects"]:
        if not has_homework(result):
            continue  # пропускаем предмет без ДЗ
        # здесь нужен метод для нахождения subject_id по имени
        subject_id = await get_subject_id_by_name(normalize_subject(result["name"]), db)

        date_str = result.get("date") or _tomorrow_str()
        description = trim_description(result["task"]["description"])
        task_hash = make_task_hash(subject_id, date_str, description)

        # # --- Проверка 1: дубликат (идентичное ДЗ) ---
        # duplicate = await get_task_by_hash(db, payload.child_id, task_hash)
        # if duplicate:
        #     results.append({
        #         "status": "duplicate",
        #         "task": duplicate
        #     })
        #     continue

        # # --- Проверка 2: ДЗ по дате и предмету ---
        # existing_task = await get_task_by_subject_date(
        #     db, payload.child_id, subject_id, date_str
        # )

        subtasks = [
            SubtaskCreate(
                title=sub["detail"],
                type=detect_category(sub["type"]),
            )
            for sub in result["task"].get("subtasks", [])
        ]

        # subs = result["task"].get("subtasks", [])
        # print(subs)

        # if existing_task:
        #     # добавляем только новые подзадачи
        #     existing_titles = {st.title for st in existing_task.subtasks}
        #     new_subs = [
        #         Subtask(title=st.title, type=st.type, status="todo", position=len(existing_task.subtasks) + i + 1)
        #         for i, st in enumerate(subtasks)
        #         if st.title not in existing_titles
        #     ]
        #     existing_task.subtasks.extend(new_subs)

        #     await db.commit()
        #     await db.refresh(existing_task, attribute_names=["subtasks"])

        #     results.append({
        #         "status": "updated",
        #         "task": existing_task
        #     })
        #     continue

        task_create = TaskCreate(
            child_id=payload.child_id,
            subject_id=subject_id,
            date=date_str,
            title=description,
            hash=task_hash,
            subtasks=subtasks
        )

        result_staus = await create_task(task_create, db, user)
        # tasks.append(task)
        results.append(result_staus)

    return results
