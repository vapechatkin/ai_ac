import json
import os
import uuid
import requests
import urllib3

from dotenv import load_dotenv

load_dotenv()

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

        self.history_file = "history.json"

        self.access_token = self._get_access_token()

        self.messages = self._load_history()

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

    def _load_history(self):
        if os.path.exists(self.history_file):
            with open(
                self.history_file,
                "r",
                encoding="utf-8"
            ) as file:
                return json.load(file)

        return [
            {
                "role": "system",
                "content": "Ты полезный AI-ассистент."
            }
        ]

    def _save_history(self):
        with open(
            self.history_file,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                self.messages,
                file,
                ensure_ascii=False,
                indent=2
            )

    def ask(self, user_message):
        self.messages.append({
            "role": "user",
            "content": user_message
        })

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

        self.messages.append({
            "role": "assistant",
            "content": assistant_message
        })

        self._save_history()

        return assistant_message
