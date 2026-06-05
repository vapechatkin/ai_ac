import os
import uuid
import json
import requests
import warnings
from jsonschema import validate, ValidationError

# =========================
# НАСТРОЙКИ
# =========================

ENV_KEY_NAME = "GIGACHAT_AUTH_KEY"

SYSTEM_PROMPT = """
Ты API-ассистент.

Всегда отвечай СТРОГО в JSON.
Не используй markdown.
Не добавляй пояснений вне JSON.

Формат ответа:

{
  "answer": "string",
  "status": "success|error",
  "sources": ["string"]
}
"""

# JSON-схема для проверки ответа
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["success", "error"]
        },
        "sources": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["answer", "status", "sources"]
}

# =========================
# ОТКЛЮЧЕНИЕ WARNING SSL
# =========================

warnings.filterwarnings(
    'ignore',
    message='Unverified HTTPS request is being made'
)

# =========================
# ПОЛУЧЕНИЕ TOKEN
# =========================

def get_token():
    """
    Получение OAuth-токена GigaChat
    """

    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    auth_key = os.getenv(ENV_KEY_NAME)

    if not auth_key:
        print(f"[ОШИБКА] Переменная окружения '{ENV_KEY_NAME}' не найдена")
        return None

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': str(uuid.uuid4()),
        'Authorization': f'Basic {auth_key}'
    }

    payload = {
        'scope': 'GIGACHAT_API_PERS'
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            data=payload,
            verify=False,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        return data.get('access_token')

    except requests.exceptions.RequestException as e:
        print(f"[ОШИБКА] Не удалось получить токен:\n{e}")
        return None


# =========================
# ЗАПРОС В GIGACHAT
# =========================

def chat(token, message):
    """
    Отправка сообщения в GigaChat API
    """

    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'RqUID': str(uuid.uuid4())
    }

    payload = {
        "model": "GigaChat",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": message
            }
        ],
        "stream": False,
        "repetition_penalty": 1,

        # Явный JSON-формат ответа
        "response_format": {
            "type": "json_object"
        }
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"[ОШИБКА] Ошибка запроса:\n{e}")
        return None


# =========================
# ПАРСИНГ И ВАЛИДАЦИЯ
# =========================

def parse_response(response_data):
    """
    Парсинг и проверка JSON-ответа модели
    """

    try:
        content = response_data['choices'][0]['message']['content']

        parsed_json = json.loads(content)

        # Проверка схемы
        validate(
            instance=parsed_json,
            schema=RESPONSE_SCHEMA
        )

        return parsed_json

    except json.JSONDecodeError:
        print("[ОШИБКА] Модель вернула невалидный JSON")
        return None

    except ValidationError as e:
        print("[ОШИБКА] JSON не соответствует схеме")
        print(e)
        return None

    except (KeyError, IndexError) as e:
        print("[ОШИБКА] Неожиданная структура ответа API")
        print(e)
        return None


# =========================
# MAIN
# =========================

if __name__ == '__main__':

    print("Получение токена...")

    token = get_token()

    if not token:
        exit(1)

    print("Токен успешно получен\n")

    user_message = input("Введите сообщение: ")

    print("\nОтправка запроса...\n")

    response_data = chat(token, user_message)

    if not response_data:
        exit(1)

    result = parse_response(response_data)

    if not result:
        exit(1)

    print("======== ОТВЕТ ========")

    print(f"Статус: {result['status']}")
    print(f"\nОтвет:\n{result['answer']}")

    print("\nИсточники:")

    if result['sources']:
        for source in result['sources']:
            print(f"- {source}")
    else:
        print("Нет")
