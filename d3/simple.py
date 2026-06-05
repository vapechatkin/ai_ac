import os
import uuid
import requests
import warnings

# --- НАСТРОЙКИ ---
# Имя переменной окружения, где хранится ключ авторизации
ENV_KEY_NAME = "GIGACHAT_AUTH_KEY"
# ------------------

# --- ОТКЛЮЧЕНИЕ ПРЕДУПРЕЖДЕНИЙ О НЕБЕЗОПАСНОМ СОЕДИНЕНИИ ---
warnings.filterwarnings('ignore', message='Unverified HTTPS request is being made')

def get_token():
    """
    Запрашивает OAuth-токен у сервера авторизации.
    Ключ авторизации (Authorization) берется из переменной окружения для безопасности.
    """
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    rq_uid = str(uuid.uuid4())
    # Получаем значение из системной переменной окружения
    auth_key = os.getenv('GIGACHAT_AUTH_KEY')

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': rq_uid,
        'Authorization': f'Basic {auth_key}' # Берем ключ из окружения
    }

    # Проверяем, что переменная окружения установлена
    if not headers['Authorization']:
        print(f"Ошибка: Переменная окружения '{ENV_KEY_NAME}' не найдена.")
        return None

    try:
        # Параметр verify=False отключает проверку SSL-сертификата.
        # Это небезопасно, используйте только для тестов!
        resp = requests.post(
            url,
            headers=headers,
            data={'scope': 'GIGACHAT_API_PERS'},
            verify=False,
            timeout=10
        )
        resp.raise_for_status() # Проверим на наличие HTTP-ошибок
        data = resp.json()
        return data.get('access_token')

    except requests.exceptions.RequestException as e:
        print(f"[ОШИБКА] Не удалось получить токен: {e}")
        return None

def chat(token, message):
    """
    Отправляет сообщение пользователя в GigaChat API и возвращает ответ.
    """
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'RqUID': str(uuid.uuid4()) # RqUID обязателен для каждого запроса к API
    }

    payload = {
        "model": "GigaChat",
        "messages": [{"role": "user", "content": message}],
        "stream": False,
        "repetition_penalty": 1
    }

    try:
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False, # Отключаем проверку сертификата и здесь
            timeout=20
        )
        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.RequestException as e:
        print(f"[ОШИБКА] Не удалось отправить сообщение: {e}")
        return None

if __name__ == '__main__':
    # 1. Получаем токен доступа
    access_token = get_token()
    if not access_token:
        print("Не удалось получить токен. Проверьте переменную окружения.")
        exit(1) # Завершаем работу скрипта с ошибкой

    # 2. Просим пользователя ввести сообщение
    user_message = input("Введите ваше сообщение: ")

    # 3. Отправляем запрос и выводим ответ
    response_data = chat(access_token, user_message)

    if response_data:
        # Пробуем безопасно извлечь текст ответа из структуры JSON
        try:
            answer = response_data['choices'][0]['message']['content']
            print("\nОтвет GigaChat:")
            print(answer)
        except (KeyError, IndexError):
            print("Получен неожиданный ответ от сервера:", response_data)
