import SwiftUI

struct SetupView: View {
    let onComplete: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                Spacer(minLength: 40)
                OnboardingStep(onComplete: onComplete)
                    .frame(maxWidth: 520)
                    .padding(.horizontal, 32)
                Spacer(minLength: 40)
            }
            .frame(maxWidth: .infinity)
        }
    }
}

struct OnboardingStep: View {
    @EnvironmentObject var orchestrator: Orchestrator
    let onComplete: () -> Void

    // Profile
    @State private var name       = ""
    @State private var occupation = ""
    @State private var grade      = ""
    @State private var stack      = ""
    // Prefs
    @State private var style      = ""
    @State private var format     = ""
    @State private var language   = ""
    @State private var extras     = ""
    // Invariants
    @State private var invariants: [Invariant] = []
    @State private var newRule    = ""
    @State private var selectedCat = invariantCategories[0].key

    private var allFilled: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty &&
        !occupation.trimmingCharacters(in: .whitespaces).isEmpty &&
        !grade.trimmingCharacters(in: .whitespaces).isEmpty &&
        !stack.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {

            Text("Настройка агента").font(.largeTitle).bold()

            // ── Профиль ────────────────────────────────────────────────────
            SectionHeader("Профиль")
            Text("Агент использует эти данные чтобы лучше понимать контекст задач.")
                .font(.subheadline).foregroundStyle(.secondary)

            LabeledField("Имя",                 text: $name)
            LabeledField("Род деятельности",    text: $occupation)
            LabeledField("Грейд",               text: $grade)
            LabeledField("Стек",                text: $stack)

            // ── Предпочтения ───────────────────────────────────────────────
            SectionHeader("Предпочтения (необязательно)")

            LabeledField("Стиль",       text: $style)
            LabeledField("Формат",      text: $format)
            LabeledField("Язык",        text: $language)
            LabeledField("Пожелания",   text: $extras)

            // ── Инварианты ─────────────────────────────────────────────────
            SectionHeader("Инварианты (необязательно)")
            Text("Правила которые агент никогда не нарушит.")
                .font(.subheadline).foregroundStyle(.secondary)

            ForEach(invariants) { inv in
                let label = invariantCategories.first { $0.key == inv.category }?.label ?? inv.category
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("[\(label)]").font(.caption).foregroundStyle(.secondary)
                        Text(inv.rule)
                    }
                    Spacer()
                    Button { remove(inv.id) } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                    }.buttonStyle(.plain)
                }
                .padding(10)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }

            HStack(alignment: .bottom, spacing: 8) {
                Picker("", selection: $selectedCat) {
                    ForEach(invariantCategories, id: \.key) { Text($0.label).tag($0.key) }
                }
                .frame(width: 160).labelsHidden()

                TextField("Правило", text: $newRule)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { addInvariant() }

                Button("Добавить") { addInvariant() }
                    .disabled(newRule.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            Button("Начать работу →") { save(); onComplete() }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .frame(maxWidth: .infinity)
                .disabled(!allFilled)
                .padding(.top, 8)
        }
        .onAppear { load() }
    }

    private func load() {
        let p = orchestrator.longTermMemory.loadProfile()
        let r = orchestrator.longTermMemory.loadPrefs()
        name       = p["name"]       ?? ""
        occupation = p["occupation"] ?? ""
        grade      = p["grade"]      ?? ""
        stack      = p["stack"]      ?? ""
        style      = r["style"]      ?? ""
        format     = r["format"]     ?? ""
        language   = r["language"]   ?? ""
        extras     = r["extras"]     ?? ""
        invariants = orchestrator.invariantMemory.load()
    }

    private func save() {
        let ltm = orchestrator.longTermMemory
        ltm.setField("name",       value: name)
        ltm.setField("occupation", value: occupation)
        ltm.setField("grade",      value: grade)
        ltm.setField("stack",      value: stack)
        if !style.isEmpty    { ltm.setPref("style",    value: style) }
        if !format.isEmpty   { ltm.setPref("format",   value: format) }
        if !language.isEmpty { ltm.setPref("language", value: language) }
        if !extras.isEmpty   { ltm.setPref("extras",   value: extras) }
        orchestrator.refresh()
    }

    private func addInvariant() {
        let rule = newRule.trimmingCharacters(in: .whitespaces)
        guard !rule.isEmpty else { return }
        _ = orchestrator.invariantMemory.add(category: selectedCat, rule: rule)
        invariants = orchestrator.invariantMemory.load()
        newRule = ""
    }

    private func remove(_ id: String) {
        orchestrator.invariantMemory.remove(id: id)
        invariants = orchestrator.invariantMemory.load()
    }
}

private struct SectionHeader: View {
    let title: String
    init(_ title: String) { self.title = title }
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.headline)
            Divider()
        }
    }
}

private struct LabeledField: View {
    let label: String
    @Binding var text: String
    init(_ label: String, text: Binding<String>) {
        self.label = label
        self._text = text
    }
    var body: some View {
        HStack {
            Text(label)
                .frame(width: 140, alignment: .trailing)
                .foregroundStyle(.secondary)
                .font(.subheadline)
            TextField(label, text: $text)
                .textFieldStyle(.roundedBorder)
        }
    }
}
