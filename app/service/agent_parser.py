from openai import AsyncOpenAI
import json
import os
from typing import List, Optional

from dotenv import load_dotenv
import os
import datetime
import re

# загрузим переменные из .env
load_dotenv()

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot run agent")
    _client = AsyncOpenAI(api_key=api_key)
    return _client
    
MODEL = 'gpt-5-mini'

async def agent_parse_homework(raw_text: str) -> dict:
    """
    Отправляет текст в OpenAI, получает JSON с title и subtasks
    """
    functions = [
        {
            "name": "parse_homework",
            "description": "Разбирает текст/файл/скриншот с домашним заданием и возвращает структуру предметов с подзадачами и датой выполнения",
            "parameters": {
                "type": "object",
                "properties": {
                "subjects": {
                    "type": "array",
                    "description": "Список предметов с заданиями",
                    "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                        "type": "string",
                        "description": "Название предмета"
                        },
                        "date": {
                        "type": "string",
                        "description": "Дата выполнения задания в формате yyyy-mm-dd"
                        },
                        "task": {
                        "type": "object",
                        "properties": {
                            "description": {
                            "type": "string",
                            "description": "Краткое описание общего задания"
                            },
                            "subtasks": {
                            "type": "array",
                            "description": "Детализированные подзадачи по предмету",
                            "items": {
                                "type": "object",
                                "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                    "theory",
                                    "exercise",
                                    "dictation",
                                    "map",
                                    "drawing",
                                    "file",
                                    "reminder",
                                    "other"
                                    ],
                                    "description": "Тип подзадачи"
                                },
                                "detail": {
                                    "type": "string",
                                    "description": "Описание подзадачи (что именно нужно сделать, исходя из текста)"
                                }
                                },
                                "required": ["type", "detail"]
                            }
                            }
                        },
                        "required": ["description", "subtasks"]
                        }
                    },
                    "required": ["name", "date", "task"]
                    }
                }
                },
                "required": ["subjects"]
            }
        }


    ]

    client = _get_client()
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": raw_text}],
        functions=functions,
        function_call={"name": "parse_homework"},
    )

        # 1. Найти дату в формате ДД.ММ.ГГГГ
    date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", raw_text)
    homework_date = None
    if date_match:
        try:
            homework_date = datetime.strptime(date_match.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass

    # content = resp["choices"][0]["message"]["function_call"]["arguments"]
    msg = resp.choices[0].message

    if msg.function_call and msg.function_call.arguments:
        content = msg.function_call.arguments
    else:
        content = msg.content  # fallback если модель не вызвала функцию

    return json.loads(content)


if __name__ == "__main__":
    import asyncio

    async def run():
        result = await agent_parse_homework(
            # '''
            #     ДЗ на 30.09.25 Матеша: стр. 106( Проверочная 1), п. 15( примеры, свойства) История Учить записанное в тетрадь; Учить записанное в тетрадь; §. 5 (пункты 1,2) - учить.; Заполнить контурную карту на странице 2-3 ("Первобытный период"), используя атлас. (Выполните все 5 заданий) Труд Дописать конспект (см. прикрепленный файл) выписать определения: линейка, рашпиль, шерхебель, рубанок, сверло. Доработать рисунок (чертеж) Принести спец. одежду - фартук! Русский подготовиться к словарному диктанту (слова "А"+"Б" на стр. 214 повторить+искусный, искусство, пейзаж, галерея, аромат, иней, безвкусный, апельсин, сверкать, объятия, необъятный, прийти, идти, долина, порхать, приду, горизонт, облака, территория, Великая Отечественная война, помощник, вдалеке, горизонт, объединить, благословить Английский выучить названия стран и национальностей см. распечатку (которые отметили),выполнить задание из файла письм.
            # '''
        '''
        Дз на 01.10.25: Матеша: стр. 106( Проверочная 1), п. 15( примеры, свойства) История Учить записанное в тетрадь; Учить записанное в тетрадь; §. 5 (пункты 1,2) - учить.; Заполнить контурную карту на странице 2-3 (\"Первобытный период\"), используя атлас. (Выполните все 5 заданий) Труд Дописать конспект (см. прикрепленный файл) выписать определения: линейка, рашпиль, шерхебель, рубанок, сверло. Доработать рисунок (чертеж) Принести спец. одежду - фартук! Русский подготовиться к словарному диктанту (слова \"А\"+\"Б\" на стр. 214 повторить+искусный, искусство, пейзаж, галерея, аромат, иней, безвкусный, апельсин, сверкать, объятия, необъятный, прийти, идти, долина, порхать, приду, горизонт, облака, территория, Великая Отечественная война, помощник, вдалеке, горизонт, объединить, благословить Английский выучить названия стран и национальностей см. распечатку (которые отметили),выполнить задание из файла письм.
        '''
        
        )

        print(f'Результат: {result}')

    asyncio.run(run())