import os
import sys
import uuid
import requests
import warnings

# --- НАСТРОЙКИ ---
ENV_KEY_NAME = "GIGACHAT_AUTH_KEY"

warnings.filterwarnings(
    'ignore',
    message='Unverified HTTPS request is being made'
)


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


def chat(token, message, temperature):

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
                "role": "user",
                "content": message
            }
        ],
        "temperature": temperature,
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
        print(f"Ошибка запроса: {e}")
        return None


if __name__ == '__main__':

    if len(sys.argv) < 2:
        print('Использование:')
        print('python gigachat.py "текст" [temperature]')
        sys.exit(1)

    # Текст запроса
    user_message = sys.argv[1]

    # Temperature
    try:
        temperature = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7

        if not 0 <= temperature <= 2:
            raise ValueError

    except ValueError:
        print("temperature должен быть числом от 0 до 2")
        sys.exit(1)

    # Получаем токен
    access_token = get_token()

    if not access_token:
        sys.exit(1)

    # Отправляем запрос
    response_data = chat(
        access_token,
        user_message,
        temperature
    )

    if response_data:
        try:
            answer = response_data['choices'][0]['message']['content']

            print("\nОтвет GigaChat:\n")
            print(answer)

        except (KeyError, IndexError):
            print("Неожиданный ответ:")
            print(response_data)
