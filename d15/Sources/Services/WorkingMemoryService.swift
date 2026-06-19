import Foundation
import SwiftData

class WorkingMemoryService {
    private let context: ModelContext

    init(context: ModelContext) {
        self.context = context
    }

    // MARK: - Fetch helpers

    private func fetchAll() -> [AgentTaskModel] {
        let d = FetchDescriptor<AgentTaskModel>(sortBy: [SortDescriptor(\.createdAt)])
        return (try? context.fetch(d)) ?? []
    }

    private func fetchCurrentModel() -> AgentTaskModel? {
        var d = FetchDescriptor<AgentTaskModel>(predicate: #Predicate { $0.isCurrent })
        d.fetchLimit = 1
        return (try? context.fetch(d))?.first
    }

    // MARK: - Public API (same as before)

    func load() -> WorkflowFile {
        let models = fetchAll()
        let tasks = models.map { $0.toAgentTask() }
        let currentId = fetchCurrentModel()?.id ?? ""
        return WorkflowFile(current: currentId, tasks: tasks)
    }

    func getCurrentTask() -> AgentTask? {
        fetchCurrentModel()?.toAgentTask()
    }

    func addTask(name: String) -> AgentTask {
        for t in fetchAll() { t.isCurrent = false }
        let model = AgentTaskModel(name: name)
        context.insert(model)
        try? context.save()
        return model.toAgentTask()
    }

    func finishPlanning(steps: [String], summary: String) -> String {
        guard let t = fetchCurrentModel() else { return "Нет текущей задачи" }
        guard t.stage == .planning else { return "Задача не на этапе planning" }
        t.plan = steps
        t.stepNotes = Array(repeating: "", count: steps.count)
        t.planningResult = summary
        t.expectedAction = .awaitingConfirm
        t.pendingResult = "**План (\(steps.count) шагов):**\n" +
            steps.enumerated().map { "  \($0.offset+1). \($0.element)" }.joined(separator: "\n")
        t.updatedAt = Date()
        try? context.save()
        return ""
    }

    func finishExecution(stepResults: [String], summary: String) -> String {
        guard let t = fetchCurrentModel() else { return "Нет текущей задачи" }
        guard t.stage == .execution else { return "Задача не на этапе execution" }
        let total = t.plan.count
        t.stepNotes = Array((stepResults + Array(repeating: "", count: total)).prefix(total))
        t.executionResult = summary
        t.expectedAction = .awaitingConfirm
        t.pendingResult = "**Выполнение завершено (\(total) шагов):**\n\(summary)"
        t.updatedAt = Date()
        try? context.save()
        return ""
    }

    func finishValidation(passed: Bool, summary: String) -> String {
        guard let t = fetchCurrentModel() else { return "Нет текущей задачи" }
        guard t.stage == .validation else { return "Задача не на этапе validation" }
        t.validationResult = summary
        t.validationPassed = passed
        t.expectedAction = .awaitingConfirm
        t.pendingResult = "\(passed ? "✓" : "✗") Валидация: \(summary)"
        t.updatedAt = Date()
        try? context.save()
        return ""
    }

    func confirmTransition() -> (String, String) {
        guard let t = fetchCurrentModel() else { return ("", "Нет активной задачи.") }
        guard t.expectedAction == .awaitingConfirm else { return ("", "Агент ещё работает над этапом '\(t.stage.rawValue)'. Дождитесь завершения перед подтверждением.") }

        switch t.stage {
        case .planning:
            guard !t.plan.isEmpty else { return ("", "План не задан.") }
            t.stage = .execution; t.stepIndex = 0
            t.expectedAction = .inProgress; t.pendingResult = ""; t.updatedAt = Date()
            try? context.save()
            return ("execution", "Переходим к выполнению. Первый шаг: \(t.plan[0])")
        case .execution:
            t.stage = .validation
            t.expectedAction = .inProgress; t.pendingResult = ""; t.updatedAt = Date()
            try? context.save()
            return ("validation", "Переходим к валидации.")
        case .validation:
            if t.validationPassed != false {
                t.stage = .done; t.expectedAction = .done; t.pendingResult = ""; t.updatedAt = Date()
                try? context.save()
                return ("done", "Задача '\(t.name)' завершена! ✓")
            } else {
                t.stage = .execution; t.stepIndex = 0
                t.expectedAction = .inProgress; t.pendingResult = ""; t.updatedAt = Date()
                try? context.save()
                return ("execution", "Валидация не пройдена. Возвращаемся к выполнению.")
            }
        case .done:
            return ("", "Задача уже завершена.")
        }
    }

    func deleteTask(id: String) {
        guard let model = fetchAll().first(where: { $0.id == id }) else { return }
        let wasCurrent = model.isCurrent
        context.delete(model)
        if wasCurrent, let next = fetchAll().first {
            next.isCurrent = true
        }
        try? context.save()
    }

    func resetForFeedback() {
        guard let t = fetchCurrentModel() else { return }
        t.expectedAction = .inProgress
        t.pendingResult = ""
        t.updatedAt = Date()
        try? context.save()
    }

    func rollback() -> (String, String) {
        guard let t = fetchCurrentModel() else { return ("", "Нет активной задачи.") }
        let prev: Stage
        switch t.stage {
        case .execution:  prev = .planning
        case .validation: prev = .execution
        case .planning: return ("", "Нельзя откатиться с этапа планирования — это первый шаг.")
        case .done:     return ("", "Задача уже завершена, откат невозможен.")
        default:        return ("", "Откат с этапа '\(t.stage.rawValue)' невозможен.")
        }
        t.stage = prev; t.expectedAction = .inProgress; t.pendingResult = ""; t.updatedAt = Date()
        try? context.save()
        return (prev.rawValue, "Откат на этап '\(prev.rawValue)'.")
    }
}
