import SwiftUI

struct ChatView: View {
    @EnvironmentObject var orchestrator: Orchestrator
    @State private var input = ""
    @State private var scrollProxy: ScrollViewProxy? = nil

    var body: some View {
        VStack(spacing: 0) {
            // ── Messages ───────────────────────────────────────────────────
            ScrollViewReader { proxy in
                ScrollView {
                    messageList
                        .padding(16)
                }
                .onChange(of: orchestrator.messages.count) { _ in
                    withAnimation { proxy.scrollTo(orchestrator.messages.last?.id, anchor: .bottom) }
                }
                .onChange(of: orchestrator.isLoading) { _ in
                    if orchestrator.isLoading {
                        withAnimation { proxy.scrollTo("loading", anchor: .bottom) }
                    }
                }
            }

            Divider()

            // ── State hint ─────────────────────────────────────────────────
            if !orchestrator.stateHint.isEmpty {
                Text(orchestrator.stateHint)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 14)
                    .padding(.top, 8)
            }

            // ── Input ──────────────────────────────────────────────────────
            HStack(alignment: .bottom, spacing: 10) {
                TextField(inputPlaceholder, text: $input, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...6)
                    .padding(10)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                    .onSubmit { send() }
                    .disabled(orchestrator.isLoading)

                Button(action: send) {
                    sendIcon
                }
                .buttonStyle(.plain)
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty || orchestrator.isLoading)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 12)
            .padding(.top, 6)
        }
        .navigationTitle(orchestrator.currentTask?.name ?? "AI Agent")
        .navigationSubtitle(orchestrator.currentTask.map { "Stage: \($0.stage.rawValue)" } ?? "")
    }

    private var inputPlaceholder: String {
        switch orchestrator.currentTask?.expectedAction {
        case .awaitingConfirm: return "Напишите что изменить или нажмите Confirm..."
        case .inProgress:      return "Агент работает, подождите..."
        case .done, nil:       return "Напишите новую задачу..."
        }
    }

    private var sendIcon: some View {
        let disabled = input.trimmingCharacters(in: .whitespaces).isEmpty || orchestrator.isLoading
        return Image(systemName: "arrow.up.circle.fill")
            .font(.system(size: 28))
            .foregroundStyle(disabled ? AnyShapeStyle(.secondary) : AnyShapeStyle(.blue))
    }

    @ViewBuilder
    private var messageList: some View {
        LazyVStack(alignment: .leading, spacing: 12) {
            ForEach(orchestrator.messages) { msg in
                MessageBubble(msg: msg).id(msg.id)
            }
            if orchestrator.isLoading {
                HStack(spacing: 8) {
                    ProgressView().scaleEffect(0.7)
                    Text("Агент работает...").foregroundStyle(.secondary).font(.subheadline)
                }
                .padding(.leading, 12)
                .id("loading")
            }
        }
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !orchestrator.isLoading else { return }
        input = ""
        Task { await orchestrator.handleUserInput(text) }
    }
}

struct MessageBubble: View {
    let msg: ChatMessage

    var isUser: Bool { msg.role == .user }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 60) }

            Text(msg.content)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    isUser
                        ? Color.accentColor.opacity(0.15)
                        : Color.primary.opacity(0.06),
                    in: RoundedRectangle(cornerRadius: 12)
                )
                .foregroundStyle(.primary)

            if !isUser { Spacer(minLength: 60) }
        }
    }
}
