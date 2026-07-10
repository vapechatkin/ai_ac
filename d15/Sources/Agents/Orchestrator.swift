import Foundation
import SwiftUI
import SwiftData

@MainActor
class Orchestrator: ObservableObject {
    @Published var messages:     [ChatMessage] = []
    @Published var currentTask:  AgentTask?
    @Published var allTasks:     [AgentTask]   = []
    @Published var isLoading     = false
    @Published var isSetupDone   = false

    let workingMemory:  WorkingMemoryService
    let longTermMemory: LongTermMemoryService
    let invariantMemory: InvariantMemoryService
    var client: (any LLMClient)?

    init(context: ModelContext) {
        workingMemory   = WorkingMemoryService(context: context)
        longTermMemory  = LongTermMemoryService(context: context)
        invariantMemory = InvariantMemoryService(context: context)

        client = OllamaClient(model: OllamaModelStorage.load())

        isSetupDone = hasProfile()
        refresh()

        if let t = currentTask, !t.pendingResult.isEmpty {
            messages.append(ChatMessage(role: .assistant, content: t.pendingResult))
        }
    }

    func hasProfile() -> Bool { longTermMemory.isComplete() }

    func setOllama(model: String) {
        OllamaModelStorage.save(model)
        client = OllamaClient(model: model)
    }

    var stateHint: String {
        guard let task = currentTask else {
            return "Напишите задачу — агент составит план, выполнит и проверит её"
        }
        switch (task.stage, task.expectedAction) {
        case (.planning, .inProgress):
            return "Агент планирует задачу..."
        case (.planning, .awaitingConfirm):
            return "Подтвердите план или напишите что изменить"
        case (.execution, .inProgress):
            return "Агент выполняет задачу..."
        case (.execution, .awaitingConfirm):
            return "Подтвердите результат или напишите что доработать"
        case (.validation, .inProgress):
            return "Агент проверяет результат..."
        case (.validation, .awaitingConfirm):
            return "Подтвердите проверку или напишите замечания"
        case (.done, _):
            return "Задача завершена. Напишите новую задачу"
        default:
            return ""
        }
    }


    func refresh() {
        let wf = workingMemory.load()
        allTasks    = wf.tasks
        currentTask = wf.tasks.first { $0.id == wf.current }
    }

    private func addMsg(_ role: MsgRole, _ text: String) {
        messages.append(ChatMessage(role: role, content: text))
    }

    // MARK: - User actions

    func handleUserInput(_ text: String) async {
        guard !text.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        addMsg(.user, text)

        let task = currentTask
        if task == nil || task?.stage == .done {
            let t = workingMemory.addTask(name: text)
            refresh()
            addMsg(.assistant, "Задача '\(t.name)' создана. Начинаю планирование...")
            await kickstart()
        } else if task?.expectedAction == .awaitingConfirm {
            await handleAwaitingConfirmChat(text, task: task!)
        } else {
            await kickstart()
        }
    }

    private func handleAwaitingConfirmChat(_ text: String, task: AgentTask) async {
        guard let c = client else { addMsg(.assistant, "LLM не настроена."); return }
        isLoading = true; defer { isLoading = false }

        let transitions: String
        switch task.stage {
        case .planning:
            transitions = "• Подтвердить план → перейти к выполнению (Confirm)\n• Удалить задачу\n• Попросить доработать план"
        case .execution:
            transitions = "• Подтвердить результат → перейти к валидации (Confirm)\n• Вернуться к планированию (Back)\n• Попросить доработать результат"
        case .validation:
            transitions = "• Завершить задачу / вернуть на выполнение (Confirm)\n• Попросить пересмотреть проверку"
        case .done:
            transitions = "• Написать новую задачу"
        }

        let reviseTool: [String: Any] = [
            "name": "revise_stage",
            "description": "Вызови ТОЛЬКО если пользователь явно просит изменить, доработать или исправить текущий результат этапа",
            "input_schema": [
                "type": "object",
                "properties": [
                    "feedback": ["type": "string", "description": "Что именно нужно изменить"]
                ],
                "required": ["feedback"]
            ]
        ]

        let system = """
            Ты координатор агентской системы. Этап задачи: \(task.stage.rawValue).

            Текущий результат этапа:
            \(task.pendingResult)

            Допустимые действия пользователя:
            \(transitions)

            Определи намерение пользователя:
            — Если одобряет, соглашается, говорит что всё готово или хочет перейти дальше —
              ответь коротко что нужно нажать Confirm. НЕ вызывай revise_stage.
            — Если просит внести изменения, правки, добавить или убрать что-то —
              вызови revise_stage с описанием изменений.
            — Если просит недопустимый переход (например, сразу завершить из planning) —
              объясни ограничения и перечисли что доступно. НЕ вызывай revise_stage.
            """

        do {
            let response = try await c.createMessage(
                system: system,
                messages: [c.userMsg(text)],
                tools: [reviseTool],
                toolChoice: nil
            )

            let textBlocks = response.content.filter { $0.type == "text" }
            let toolBlocks = response.content.filter { $0.type == "tool_use" }

            if let revise = toolBlocks.first(where: { $0.name == "revise_stage" }) {
                let feedback = (revise.inputDict["feedback"] as? String) ?? text
                addMsg(.assistant, "Дорабатываю с учётом ваших правок...")
                workingMemory.resetForFeedback()
                refresh()
                await kickstart(feedback: feedback)
            } else if let reply = textBlocks.first?.text, !reply.isEmpty {
                addMsg(.assistant, reply)
            }
        } catch {
            addMsg(.assistant, "Ошибка: \(error.localizedDescription)")
        }
    }

    func deleteTask(id: String) {
        workingMemory.deleteTask(id: id)
        refresh()
        messages.removeAll()
        if let t = currentTask, !t.pendingResult.isEmpty {
            messages.append(ChatMessage(role: .assistant, content: t.pendingResult))
        }
    }

    func handleConfirm() async {
        let (newStage, msg) = workingMemory.confirmTransition()
        refresh()
        addMsg(.assistant, msg)
        if !newStage.isEmpty && newStage != "done" { await kickstart() }
    }

    func handleBack() async {
        let (newStage, msg) = workingMemory.rollback()
        refresh()
        addMsg(.assistant, msg)
        if !newStage.isEmpty { await kickstart() }
    }

    func kickstart(feedback: String = "") async {
        guard let task = workingMemory.getCurrentTask() else { return }
        let profile  = longTermMemory.toPromptText()
        let prefs    = longTermMemory.prefsToPromptText()
        let invBlock = invariantMemory.toPromptBlock()

        switch task.stage {
        case .planning:   await runPlanningAgent(task, profile, prefs, invBlock, feedback: feedback)
        case .execution:  await runExecutionAgent(task, profile, prefs, invBlock, feedback: feedback)
        case .validation: await runValidationAgent(task, profile, prefs, invBlock, feedback: feedback)
        case .done: break
        }
    }

    // MARK: - Agents

    private func runPlanningAgent(_ task: AgentTask, _ profile: String, _ prefs: String, _ invBlock: String, feedback: String = "") async {
        guard let c = client else { addMsg(.assistant, "LLM не настроена."); return }
        isLoading = true; defer { isLoading = false }

        let system = buildSystem(invBlock, profile, prefs, """
            Ты агент-планировщик. Составь детальный план выполнения задачи.
            - Разбей задачу на конкретные шаги
            - Проверяй каждый шаг на соответствие инвариантам
            - Когда план готов — СРАЗУ вызови finish_planning
            - Не задавай вопросов пользователю

            ПРАВИЛА КОНЕЧНОГО АВТОМАТА (этап: planning):
            Допустимые переходы из текущего этапа:
              • planning → execution (пользователь нажимает Confirm)
              • задача удаляется (пользователь нажимает кнопку удаления)
            ЗАПРЕЩЕНО: переходить в validation, done или пропускать этапы.
            Если пользователь просит завершить задачу, пометить как выполненную или пропустить этапы —
            объясни, что сейчас возможны только два действия: подтвердить план (перейти к выполнению) или удалить задачу.
            Если пользователь даёт правки к плану — учти их и вызови finish_planning с обновлённым планом.
            """)
        var prompt = "Создай план для задачи:\n\n\(task.name)"
        if !feedback.isEmpty { prompt += "\n\nКомментарий пользователя к предыдущему варианту:\n\(feedback)" }
        var history = [c.userMsg(prompt)]

        do {
            try await runLoop(c, system, &history, [AgentTools.finishPlanning], ["finish_planning"]) { name, input in
                guard name == "finish_planning" else { return "Unknown tool" }
                let steps   = (input["steps"] as? [String]) ?? []
                let summary = (input["summary"] as? String) ?? ""
                let err = self.workingMemory.finishPlanning(steps: steps, summary: summary)
                return err.isEmpty ? "OK" : err
            }
            refresh()
            if let pr = currentTask?.pendingResult, !pr.isEmpty { addMsg(.assistant, pr) }
        } catch {
            addMsg(.assistant, "Ошибка агента планирования: \(error.localizedDescription)")
        }
    }

    private func runExecutionAgent(_ task: AgentTask, _ profile: String, _ prefs: String, _ invBlock: String, feedback: String = "") async {
        guard let c = client else { addMsg(.assistant, "LLM не настроена."); return }
        isLoading = true; defer { isLoading = false }

        let system = buildSystem(invBlock, profile, prefs, """
            Ты агент-исполнитель. Выполни все шаги плана и отчитайся.
            - Выполни КАЖДЫЙ шаг плана без пропусков
            - Для каждого шага предоставь конкретный результат
            - Когда ВСЕ шаги выполнены — вызови finish_execution
            - Проверяй каждое действие на соответствие инвариантам

            ПРАВИЛА КОНЕЧНОГО АВТОМАТА (этап: execution):
            Допустимые переходы из текущего этапа:
              • execution → validation (пользователь нажимает Confirm)
              • execution → planning (пользователь нажимает Back)
              • задача удаляется (пользователь нажимает кнопку удаления)
            ЗАПРЕЩЕНО: переходить сразу в done, пропускать валидацию.
            Если пользователь просит завершить задачу или пропустить проверку —
            объясни, что после выполнения обязательно следует этап валидации, пропустить его нельзя.
            Если пользователь просит доработать результат — учти замечания и вызови finish_execution с обновлёнными результатами.
            """)
        let planStr = task.plan.enumerated().map { "\($0.offset+1). \($0.element)" }.joined(separator: "\n")
        var prompt = "Выполни все шаги:\n\nЗадача: \(task.name)\n\nПлан:\n\(planStr)"
        if !feedback.isEmpty { prompt += "\n\nКомментарий пользователя:\n\(feedback)" }
        var history = [c.userMsg(prompt)]

        do {
            try await runLoop(c, system, &history, [AgentTools.finishExecution], ["finish_execution"]) { name, input in
                guard name == "finish_execution" else { return "Unknown tool" }
                let results = (input["step_results"] as? [String]) ?? []
                let summary = (input["summary"] as? String) ?? ""
                let err = self.workingMemory.finishExecution(stepResults: results, summary: summary)
                return err.isEmpty ? "OK" : err
            }
            refresh()
            if let pr = currentTask?.pendingResult, !pr.isEmpty { addMsg(.assistant, pr) }
        } catch {
            addMsg(.assistant, "Ошибка агента выполнения: \(error.localizedDescription)")
        }
    }

    private func runValidationAgent(_ task: AgentTask, _ profile: String, _ prefs: String, _ invBlock: String, feedback: String = "") async {
        guard let c = client else { addMsg(.assistant, "LLM не настроена."); return }
        isLoading = true; defer { isLoading = false }

        let system = buildSystem(invBlock, profile, prefs, """
            Ты агент-валидатор. Проверь качество выполнения задачи.
            - Проверь каждый шаг на соответствие плану
            - Нарушение инварианта = автоматически passed=false
            - Когда проверка завершена — вызови finish_validation

            ПРАВИЛА КОНЕЧНОГО АВТОМАТА (этап: validation):
            Допустимые переходы из текущего этапа:
              • validation → done (если passed=true, пользователь нажимает Confirm)
              • validation → execution (если passed=false или пользователь нажимает Confirm после провала)
              • задача удаляется (пользователь нажимает кнопку удаления)
            ЗАПРЕЩЕНО: переходить обратно в planning напрямую, пропускать подтверждение.
            Если пользователь просит пропустить проверку или сразу завершить —
            объясни, что только после валидации (passed=true) задача может быть завершена, иначе вернётся на выполнение.
            Если пользователь указывает на ошибки в проверке — учти замечания и вызови finish_validation с обновлённым результатом.
            """)
        let planStr  = task.plan.enumerated().map { "\($0.offset+1). \($0.element)" }.joined(separator: "\n")
        let notesStr = task.stepNotes.enumerated().map { "\($0.offset+1). \($0.element)" }.joined(separator: "\n")
        let execInfo = notesStr.isEmpty ? task.stageResults.execution : notesStr
        var prompt   = "Проверь выполнение:\n\nЗадача: \(task.name)\n\nПлан:\n\(planStr)\n\nРезультаты:\n\(execInfo)"
        if !feedback.isEmpty { prompt += "\n\nКомментарий пользователя:\n\(feedback)" }
        var history  = [c.userMsg(prompt)]

        do {
            try await runLoop(c, system, &history, [AgentTools.finishValidation], ["finish_validation"]) { name, input in
                guard name == "finish_validation" else { return "Unknown tool" }
                let passed  = (input["passed"]  as? Bool)   ?? false
                let summary = (input["summary"] as? String) ?? ""
                let err = self.workingMemory.finishValidation(passed: passed, summary: summary)
                return err.isEmpty ? "OK" : err
            }
            refresh()
            if let pr = currentTask?.pendingResult, !pr.isEmpty { addMsg(.assistant, pr) }
        } catch {
            addMsg(.assistant, "Ошибка агента валидации: \(error.localizedDescription)")
        }
    }

    // MARK: - Agent loop

    private func runLoop(
        _ client: any LLMClient,
        _ system: String,
        _ history: inout [[String: Any]],
        _ tools: [[String: Any]],
        _ finishTools: Set<String>,
        executor: (String, [String: Any]) throws -> String
    ) async throws {
        var nudged = false

        while true {
            let toolChoice: [String: Any]? = nudged ? ["type": "any"] : nil
            let response = try await client.createMessage(
                system: system, messages: history,
                tools: tools, toolChoice: toolChoice
            )

            history.append(client.assistantMsg(response.content))

            let toolBlocks = response.content.filter { $0.type == "tool_use" }
            if toolBlocks.isEmpty {
                if !nudged { nudged = true; continue }
                return
            }

            var results: [[String: Any]] = []
            var calledFinish = false

            for block in toolBlocks {
                guard let id = block.id, let name = block.name else { continue }
                let result = try executor(name, block.inputDict)
                results.append(["type": "tool_result", "tool_use_id": id, "content": result])
                if finishTools.contains(name) { calledFinish = true }
            }

            history.append(client.toolResultMsg(toolUseId: results.first?["tool_use_id"] as? String ?? "", result: ""))
            // Append all tool results properly
            history.removeLast()
            history.append(["role": "user", "content": results])

            if calledFinish { return }
            nudged = false
        }
    }

    private func buildSystem(_ inv: String, _ profile: String, _ prefs: String, _ instructions: String) -> String {
        var parts: [String] = []
        if !inv.isEmpty     { parts.append(inv) }
        parts.append("Профиль пользователя:\n\(profile)")
        if !prefs.isEmpty   { parts.append("Предпочтения:\n\(prefs)") }
        parts.append(instructions)
        return parts.joined(separator: "\n\n")
    }
}
