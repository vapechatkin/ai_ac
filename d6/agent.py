import os
import uuid
import requests
import urllib3

from dotenv import load_dotenv

load_dotenv()

# отключаем spam warning про SSL
urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


class Agent:
    def __init__(self):
        self.credentials = os.getenv("GIGACHAT_CREDENTIALS")

        self.auth_url = (
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        )

        self.chat_url = (
            "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        )

        self.access_token = self._get_access_token()

        # история сессии
        self.messages = [
            {
                "role": "system",
                "content": "Ты полезный AI-ассистент."
            }
        ]

    def _get_access_token(self):
        headers = {
            "Authorization": f"Basic {self.credentials}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded"
        }

        payload = {
            "scope": "GIGACHAT_API_PERS"
        }

        response = requests.post(
            self.auth_url,
            headers=headers,
            data=payload,
            verify=False
        )

        response.raise_for_status()

        data = response.json()

        return data["access_token"]

    def ask(self, user_message):
        # сохраняем сообщение пользователя
        self.messages.append({
            "role": "user",
            "content": user_message
        })

        # показываем историю перед запросом
        print("\n========== HISTORY ==========")

        for message in self.messages:
            print(message)

        print("========== HISTORY END ==========\n")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "GigaChat",
            "messages": self.messages,
            "temperature": 0.7
        }

        response = requests.post(
            self.chat_url,
            headers=headers,
            json=payload,
            verify=False
        )

        response.raise_for_status()

        data = response.json()

        assistant_message = (
            data["choices"][0]["message"]["content"]
        )

        # сохраняем ответ модели
        self.messages.append({
            "role": "assistant",
            "content": assistant_message
        })

        return assistant_message
