
import os
import uuid
import requests
import warnings

# --- НАСТРОЙКИ ---
# Имя переменной окружения, где хранится ключ авторизации
ENV_KEY_NAME = "GIGACHAT_AUTH_KEY"
# ------------------

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = (
    "Отвечай кратко. "
    "Максимальная длина ответа — 30 символов."
)
# ---------------------

# --- ОТКЛЮЧЕНИЕ ПРЕДУПРЕЖДЕНИЙ О НЕБЕЗОПАСНОМ СОЕДИНЕНИИ ---
warnings.filterwarnings(
    'ignore',
    message='Unverified HTTPS request is being made'
)

def get_token():
    """
    Запрашивает OAuth-токен у сервера авторизации.
    Ключ авторизации (Authorization) берется из переменной окружения.
    """

    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    rq_uid = str(uuid.uuid4())

    # Получаем значение из переменной окружения
    auth_key = os.getenv(ENV_KEY_NAME)

    if not auth_key:
        print(f"Ошибка: Переменная окружения '{ENV_KEY_NAME}' не найдена.")
        return None

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': rq_uid,
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

        data = response.json()

        return data.get('access_token')

    except requests.exceptions.RequestException as e:
        print(f"[ОШИБКА] Не удалось получить токен:\n{e}")
        return None


def chat(token, message):
    """
    Отправляет сообщение пользователя в GigaChat API
    и возвращает ответ.
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
        "repetition_penalty": 1
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=20
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"[ОШИБКА] Не удалось отправить сообщение:\n{e}")
        return None


if __name__ == '__main__':

    # 1. Получаем токен доступа
    access_token = get_token()

    if not access_token:
        print("Не удалось получить токен.")
        exit(1)

    # 2. Получаем сообщение пользователя
    user_message = input("Введите ваше сообщение: ")

    # 3. Отправляем запрос
    response_data = chat(access_token, user_message)

    # 4. Выводим ответ
    if response_data:
        try:
            answer = response_data['choices'][0]['message']['content']

            print("\nОтвет GigaChat:")
            print(answer)

        except (KeyError, IndexError):
            print("Получен неожиданный ответ от сервера:")
            print(response_data)

