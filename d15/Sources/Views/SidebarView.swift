import SwiftUI

struct SidebarView: View {
    @EnvironmentObject var orchestrator: Orchestrator
    @Binding var showMemory: Bool
    @State private var showNewTask = false
    @State private var newTaskName = ""

    var body: some View {
        List {
            // ── Текущая задача ─────────────────────────────────────────────
            if let task = orchestrator.currentTask {
                Section("Текущая задача") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(task.name)
                            .font(.headline)
                            .lineLimit(3)

                        HStack(spacing: 6) {
                            StageTag(task.stage)
                            if task.expectedAction == .awaitingConfirm {
                                Text("ждёт подтверждения")
                                    .font(.caption2)
                                    .foregroundStyle(.orange)
                            }
                        }


                    }
                    .padding(.vertical, 4)

                    if task.expectedAction == .awaitingConfirm {
                        Button {
                            Task { await orchestrator.handleConfirm() }
                        } label: {
                            Label("Confirm", systemImage: "checkmark.circle.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                        .disabled(orchestrator.isLoading)
                    }

                    if task.stage != .planning && task.stage != .done {
                        Button {
                            Task { await orchestrator.handleBack() }
                        } label: {
                            Label("Back", systemImage: "arrow.uturn.backward")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(orchestrator.isLoading)
                    }
                }
            }

            // ── Все задачи ─────────────────────────────────────────────────
            Section {
                if orchestrator.allTasks.isEmpty && !showNewTask {
                    Text("Нет задач")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                } else {
                    ForEach(orchestrator.allTasks) { task in
                        TaskRow(task: task)
                    }
                }

                if showNewTask {
                    HStack {
                        TextField("Название задачи", text: $newTaskName)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit { commitNewTask() }
                        Button { commitNewTask() } label: {
                            Image(systemName: "checkmark")
                        }
                        .disabled(newTaskName.trimmingCharacters(in: .whitespaces).isEmpty)
                        Button { showNewTask = false; newTaskName = "" } label: {
                            Image(systemName: "xmark")
                        }
                    }
                }
            } header: {
                HStack {
                    Text("Задачи (\(orchestrator.allTasks.count))")
                    Spacer()
                    Button { showNewTask = true } label: {
                        Image(systemName: "plus")
                            .font(.caption).bold()
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .listStyle(.sidebar)
        .safeAreaInset(edge: .bottom) {
            Button {
                showMemory = true
            } label: {
                Label("Профиль и инварианты", systemImage: "person.crop.circle")
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .font(.subheadline)
            }
            .buttonStyle(.plain)
            .padding(12)
            .background(.bar)
        }
    }

    private func commitNewTask() {
        let name = newTaskName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        showNewTask = false
        newTaskName = ""
        Task { await orchestrator.handleUserInput(name) }
    }
}

struct TaskRow: View {
    @EnvironmentObject var orchestrator: Orchestrator
    let task: AgentTask
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 6) {
            StageTag(task.stage)
            Text(task.name)
                .font(.caption)
                .lineLimit(2)
            Spacer()
            if isHovered {
                Button {
                    orchestrator.deleteTask(id: task.id)
                } label: {
                    Image(systemName: "trash")
                        .font(.caption)
                        .foregroundStyle(.red.opacity(0.8))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 2)
        .opacity(task.id == orchestrator.currentTask?.id ? 1 : 0.6)
        .onHover { isHovered = $0 }
    }
}

struct StageTag: View {
    let stage: Stage
    init(_ stage: Stage) { self.stage = stage }

    var color: Color {
        switch stage {
        case .planning:   return .green
        case .execution:  return .blue
        case .validation: return .orange
        case .done:       return .secondary
        }
    }

    var body: some View {
        Text(stage.rawValue)
            .font(.caption2).bold()
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }
}
