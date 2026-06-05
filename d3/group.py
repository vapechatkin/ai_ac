import os
import uuid
import requests
import warnings

# --- НАСТРОЙКИ ---
ENV_KEY_NAME = "GIGACHAT_AUTH_KEY"

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
Ты группа экспертов, состоящая из:

1. Аналитика
2. Инженера
3. Критика

Каждый эксперт должен дать отдельный ответ.

Формат ответа:

[Аналитик]
текст ответа

[Инженер]
текст ответа

[Критик]
текст ответа
"""
# ---------------------

# --- ОТКЛЮЧЕНИЕ WARNING SSL ---
warnings.filterwarnings(
    'ignore',
    message='Unverified HTTPS request is being made'
)

def get_token():
    """
    Получение OAuth-токена
    """

    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    auth_key = os.getenv(ENV_KEY_NAME)

    if not auth_key:
        print(f"Ошибка: переменная '{ENV_KEY_NAME}' не найдена")
        return None

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': str(uuid.uuid4()),
        'Authorization': f'Basic {auth_key}'
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            data={'scope': 'GIGACHAT_API_PERS'},
            verify=False,
            timeout=10
        )

        response.raise_for_status()

        return response.json().get('access_token')

    except requests.exceptions.RequestException as e:
        print(f"[ОШИБКА] Не удалось получить токен:\n{e}")
        return None


def chat(token, message):
    """
    Запрос к GigaChat API
    """

    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'RqUID': str(uuid.uuid4())
    }

    payload = {
        "model": "GigaChat-Pro",
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


if __name__ == '__main__':

    # Получаем токен
    access_token = get_token()

    if not access_token:
        exit(1)

    # Ввод пользователя
    user_message = input("Введите запрос: ")

    # Запрос к модели
    response_data = chat(access_token, user_message)

    # Вывод ответа
    if response_data:
        try:
            answer = response_data['choices'][0]['message']['content']

            print("\n===== ОТВЕТ ЭКСПЕРТОВ =====\n")
            print(answer)

        except (KeyError, IndexError):
            print("Неожиданный ответ сервера:")
            print(response_data)
