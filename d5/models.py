import os
import sys
import uuid
import time
import requests
import warnings

# =========================
# НАСТРОЙКИ
# =========================

ENV_KEY_NAME = "GIGACHAT_AUTH_KEY"

# =========================
# АКТУАЛЬНЫЕ ТАРИФЫ
# Цена за 1 токен
# =========================

MODEL_PRICES = {
    "GigaChat-2": 1300 / 20_000_000,
    "GigaChat-2-Pro": 1500 / 3_000_000,
    "GigaChat-2-Max": 1950 / 3_000_000
}

# Отключение SSL warning
warnings.filterwarnings(
    'ignore',
    message='Unverified HTTPS request is being made'
)

# =========================
# ПОЛУЧЕНИЕ ТОКЕНА
# =========================

def get_token():

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

        print(f"Ошибка получения токена: {e}")
        return None

# =========================
# ЗАПРОС В GIGACHAT
# =========================

def chat(token, message, model):

    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'RqUID': str(uuid.uuid4())
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": message
            }
        ],
        "stream": False,
        "repetition_penalty": 1
    }

    try:

        start_time = time.time()

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=60
        )

        end_time = time.time()

        response.raise_for_status()

        elapsed = round(end_time - start_time, 2)

        return response.json(), elapsed

    except requests.exceptions.RequestException as e:

        print(f"Ошибка запроса: {e}")
        return None, None

# =========================
# РАСЧЕТ СТОИМОСТИ
# =========================

def calculate_price(model, total_tokens):

    price_per_token = MODEL_PRICES.get(model)

    if price_per_token is None:
        return 0

    cost = total_tokens * price_per_token

    return round(cost, 6)

# =========================
# MAIN
# =========================

if __name__ == '__main__':

    if len(sys.argv) < 2:

        print('\nИспользование:')
        print('python3 temp.py "текст" [model]\n')

        sys.exit(1)

    # Текст запроса
    user_message = sys.argv[1]

    # Модель
    model = sys.argv[2] if len(sys.argv) > 2 else "GigaChat-2"

    # Получение токена
    access_token = get_token()

    if not access_token:
        sys.exit(1)

    print(f"\nМодель: {model}")

    # Запрос
    response_data, elapsed = chat(
        access_token,
        user_message,
        model
    )

    if response_data:

        try:

            answer = response_data['choices'][0]['message']['content']

            usage = response_data.get("usage", {})

            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            price = calculate_price(model, total_tokens)

            print("\n========================")
            print("ОТВЕТ GIGACHAT")
            print("========================\n")

            print(answer)

            print("\n========================")
            print("СТАТИСТИКА")
            print("========================\n")

            print(f"Время ответа: {elapsed} сек")
            print(f"Prompt tokens: {prompt_tokens}")
            print(f"Completion tokens: {completion_tokens}")
            print(f"Total tokens: {total_tokens}")
            print(f"Стоимость запроса: {price} ₽")

        except (KeyError, IndexError):

            print("Неожиданный ответ:")
            print(response_data)