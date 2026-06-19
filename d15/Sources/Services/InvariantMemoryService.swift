import Foundation
import SwiftData

let invariantCategories: [(key: String, label: String)] = [
    ("arch",     "Архитектура"),
    ("tech",     "Технические решения"),
    ("stack",    "Стек"),
    ("business", "Бизнес-правила"),
    ("other",    "Прочее")
]

class InvariantMemoryService {
    private let context: ModelContext

    init(context: ModelContext) {
        self.context = context
    }

    private func fetchAll() -> [InvariantModel] {
        let d = FetchDescriptor<InvariantModel>(sortBy: [SortDescriptor(\.createdAt)])
        return (try? context.fetch(d)) ?? []
    }

    func load() -> [Invariant] {
        fetchAll().map { $0.toInvariant() }
    }

    @discardableResult
    func add(category: String, rule: String) -> Invariant {
        let model = InvariantModel(category: category, rule: rule)
        context.insert(model)
        try? context.save()
        return model.toInvariant()
    }

    @discardableResult
    func remove(id: String) -> Bool {
        guard let model = fetchAll().first(where: { $0.id == id }) else { return false }
        context.delete(model)
        try? context.save()
        return true
    }

    func toPromptBlock() -> String {
        let invs = load()
        guard !invs.isEmpty else { return "" }
        var lines = [
            "## ИНВАРИАНТЫ",
            "Следующие правила НЕЛЬЗЯ нарушать ни при каких обстоятельствах.",
            "Если запрос нарушает инвариант — ОТКАЖИ и явно назови нарушенный инвариант.",
            ""
        ]
        for inv in invs {
            let label = invariantCategories.first { $0.key == inv.category }?.label ?? inv.category
            lines.append("[\(label)] \(inv.rule)")
        }
        return lines.joined(separator: "\n")
    }
}
