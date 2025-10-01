from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import TaskCreate, SubtaskCreate
from app.routers.tasks import create_task, make_task_hash
from app.routers.subjects import get_subject_id_by_name
from app.service.agent_parser import agent_parse_homework
from datetime import datetime, timedelta
from rapidfuzz import process
import re


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


async def process_import_homework(session: AsyncSession, job) -> dict:
    """
    Обработка job с типом import_homework.
    job.payload = {"text": "...", "child_id": 123}
    """
    payload = job.payload
    raw_text = payload.get("text")
    child_id = payload.get("child_id")

    if not raw_text:
        raise ValueError("No homework content provided")

    # вызов AI-агента
    ai_results = await agent_parse_homework(raw_text)

    results = []
    for result in ai_results["subjects"]:
        if not has_homework(result):
            continue

        subject_id = await get_subject_id_by_name(
            normalize_subject(result["name"]), session
        )

        date_str = result.get("date") or _tomorrow_str()
        description = trim_description(result["task"]["description"])
        task_hash = make_task_hash(subject_id, date_str, description)

        # subtasks
        subtasks = [
            SubtaskCreate(
                title=sub["detail"],
                type=detect_category(sub["type"]),
            )
            for sub in result["task"].get("subtasks", [])
        ]

        task_create = TaskCreate(
            child_id=child_id,
            subject_id=subject_id,
            date=date_str,
            title=description,
            hash=task_hash,
            subtasks=subtasks,
        )

        # создаём задание
        task_status = await create_task(task_create, session, job.user)
        results.append(task_status)

    return {"tasks_created": len(results)}
