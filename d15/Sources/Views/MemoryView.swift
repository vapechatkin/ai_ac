import SwiftUI

struct MemoryView: View {
    @EnvironmentObject var orchestrator: Orchestrator
    @Environment(\.dismiss) private var dismiss

    @State private var profileValues: [String: String] = [:]
    @State private var prefValues:    [String: String] = [:]
    @State private var invariants:    [Invariant]      = []
    @State private var newRule        = ""
    @State private var selectedCat    = invariantCategories[0].key
    @State private var tab            = 0

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Память агента").font(.headline)
                Spacer()
                Button("Готово") { dismiss() }.keyboardShortcut(.return)
            }
            .padding()

            Divider()

            // Tabs
            Picker("", selection: $tab) {
                Text("Профиль").tag(0)
                Text("Инварианты").tag(1)
            }
            .pickerStyle(.segmented)
            .padding()

            Divider()

            ScrollView {
                if tab == 0 { profileTab } else { invariantsTab }
            }
        }
        .frame(width: 520, height: 560)
        .onAppear { load() }
    }

    // MARK: - Profile tab

    private var profileTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Group {
                Text("Профиль").font(.headline)
                ForEach(profileFields, id: \.key) { f in
                    LabeledEditField(label: f.label, text: binding(f.key, $profileValues))
                }
                Divider()
                Text("Предпочтения").font(.headline)
                ForEach(prefFields, id: \.key) { f in
                    LabeledEditField(label: f.label, text: binding(f.key, $prefValues))
                }
            }

            Button("Сохранить") { saveProfile() }
                .buttonStyle(.borderedProminent)
                .frame(maxWidth: .infinity)
        }
        .padding()
    }

    // MARK: - Invariants tab

    private var invariantsTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Инварианты (\(invariants.count))").font(.headline)

            ForEach(invariants) { inv in
                let label = invariantCategories.first { $0.key == inv.category }?.label ?? inv.category
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("[\(label)]").font(.caption).foregroundStyle(.secondary)
                        Text(inv.rule)
                    }
                    Spacer()
                    Button {
                        orchestrator.invariantMemory.remove(id: inv.id)
                        invariants = orchestrator.invariantMemory.load()
                    } label: {
                        Image(systemName: "trash").foregroundStyle(.red)
                    }.buttonStyle(.plain)
                }
                .padding(10)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
            }

            Divider()
            Text("Добавить инвариант").font(.subheadline).foregroundStyle(.secondary)

            HStack(alignment: .bottom, spacing: 8) {
                Picker("Категория", selection: $selectedCat) {
                    ForEach(invariantCategories, id: \.key) { Text($0.label).tag($0.key) }
                }
                .frame(width: 160)

                TextField("Правило", text: $newRule)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { addInvariant() }

                Button("Добавить") { addInvariant() }
                    .disabled(newRule.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding()
    }

    // MARK: - Helpers

    private func load() {
        let p = orchestrator.longTermMemory.loadProfile()
        let r = orchestrator.longTermMemory.loadPrefs()
        profileFields.forEach { profileValues[$0.key] = p[$0.key] ?? "" }
        prefFields.forEach    { prefValues[$0.key]    = r[$0.key] ?? "" }
        invariants = orchestrator.invariantMemory.load()
    }

    private func saveProfile() {
        profileFields.forEach { orchestrator.longTermMemory.setField($0.key, value: profileValues[$0.key] ?? "") }
        prefFields.forEach {
            let v = prefValues[$0.key] ?? ""
            if !v.isEmpty { orchestrator.longTermMemory.setPref($0.key, value: v) }
        }
    }

    private func addInvariant() {
        let rule = newRule.trimmingCharacters(in: .whitespaces)
        guard !rule.isEmpty else { return }
        orchestrator.invariantMemory.add(category: selectedCat, rule: rule)
        invariants = orchestrator.invariantMemory.load()
        newRule = ""
    }

    private func binding(_ key: String, _ dict: Binding<[String: String]>) -> Binding<String> {
        Binding(get: { dict.wrappedValue[key] ?? "" }, set: { dict.wrappedValue[key] = $0 })
    }
}

private struct LabeledEditField: View {
    let label: String
    @Binding var text: String
    var body: some View {
        HStack {
            Text(label).frame(width: 140, alignment: .trailing).foregroundStyle(.secondary).font(.subheadline)
            TextField(label, text: $text).textFieldStyle(.roundedBorder)
        }
    }
}
