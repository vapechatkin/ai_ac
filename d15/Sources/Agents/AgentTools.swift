import Foundation

enum AgentTools {
    static let finishPlanning: [String: Any] = [
        "name": "finish_planning",
        "description": "Сохранить готовый план. Вызови когда план полностью составлен.",
        "input_schema": [
            "type": "object",
            "properties": [
                "steps":   ["type": "array", "items": ["type": "string"], "description": "Шаги плана"],
                "summary": ["type": "string", "description": "Краткое описание плана"]
            ],
            "required": ["steps", "summary"]
        ] as [String: Any]
    ]

    static let finishExecution: [String: Any] = [
        "name": "finish_execution",
        "description": "Сообщить о завершении выполнения всех шагов.",
        "input_schema": [
            "type": "object",
            "properties": [
                "step_results": ["type": "array", "items": ["type": "string"], "description": "Результат каждого шага"],
                "summary":      ["type": "string", "description": "Итоговое резюме"]
            ],
            "required": ["step_results", "summary"]
        ] as [String: Any]
    ]

    static let finishValidation: [String: Any] = [
        "name": "finish_validation",
        "description": "Сообщить о завершении валидации.",
        "input_schema": [
            "type": "object",
            "properties": [
                "passed":  ["type": "boolean", "description": "true если прошла, false если нет"],
                "summary": ["type": "string",  "description": "Резюме валидации"]
            ],
            "required": ["passed", "summary"]
        ] as [String: Any]
    ]
}
