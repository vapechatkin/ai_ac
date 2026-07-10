# d27 — Локальная LLM в десктопном приложении

Интеграция Ollama в SwiftUI-агент из d15.

## Что сделано

Добавлен протокол `LLMClient` — общий интерфейс для LLM-клиентов.  
Реализован `OllamaClient` — отправляет запросы на `localhost:11434/api/chat`.  
Приложение работает полностью локально, без облачных моделей.

## Архитектура

```
SetupView
  └── поле "Модель Ollama" (по умолчанию qwen2.5:0.5b)

Orchestrator
  └── client: any LLMClient → OllamaClient
        └── POST http://localhost:11434/api/chat
```

## Запуск

```bash
# 1. Убедиться что Ollama запущена
ollama serve

# 2. Собрать и запустить приложение
cd d15
swift run
```

В экране настройки указать имя модели (например `qwen2.5:0.5b`) и заполнить профиль.

## Изменённые файлы (d15)

- `Sources/Services/LLMClient.swift` — протокол
- `Sources/Services/OllamaClient.swift` — клиент для Ollama
- `Sources/Services/OllamaModelStorage.swift` — сохранение имени модели
- `Sources/Agents/Orchestrator.swift` — `client: any LLMClient`, `setOllama()`
- `Sources/Views/SetupView.swift` — поле для имени модели Ollama
