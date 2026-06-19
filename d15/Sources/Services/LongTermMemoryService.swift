import Foundation
import SwiftData

let profileFields: [(key: String, label: String)] = [
    ("name",       "Имя"),
    ("occupation", "Род деятельности"),
    ("grade",      "Грейд"),
    ("stack",      "Стек")
]

let prefFields: [(key: String, label: String)] = [
    ("style",    "Стиль"),
    ("format",   "Формат"),
    ("language", "Язык"),
    ("extras",   "Пожелания")
]

class LongTermMemoryService {
    private let context: ModelContext

    init(context: ModelContext) {
        self.context = context
    }

    private func fetchProfile() -> UserProfileModel {
        var d = FetchDescriptor<UserProfileModel>()
        d.fetchLimit = 1
        if let existing = (try? context.fetch(d))?.first { return existing }
        let new = UserProfileModel()
        context.insert(new)
        try? context.save()
        return new
    }

    func loadProfile() -> [String: String] {
        let p = fetchProfile()
        return ["name": p.name, "occupation": p.occupation, "grade": p.grade, "stack": p.stack]
    }

    func loadPrefs() -> [String: String] {
        let p = fetchProfile()
        return ["style": p.style, "format": p.format, "language": p.language, "extras": p.extras]
    }

    func setField(_ key: String, value: String) {
        let p = fetchProfile()
        switch key {
        case "name":       p.name = value
        case "occupation": p.occupation = value
        case "grade":      p.grade = value
        case "stack":      p.stack = value
        default: break
        }
        try? context.save()
    }

    func setPref(_ key: String, value: String) {
        let p = fetchProfile()
        switch key {
        case "style":    p.style = value
        case "format":   p.format = value
        case "language": p.language = value
        case "extras":   p.extras = value
        default: break
        }
        try? context.save()
    }

    func isComplete() -> Bool {
        let p = fetchProfile()
        return [p.name, p.occupation, p.grade, p.stack].allSatisfy { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    func toPromptText() -> String {
        let p = loadProfile()
        return profileFields.map { "\($0.label): \(p[$0.key] ?? "(не указано)")" }.joined(separator: "\n")
    }

    func prefsToPromptText() -> String {
        let r = loadPrefs()
        return prefFields.compactMap { pair -> String? in
            guard let v = r[pair.key], !v.isEmpty else { return nil }
            return "- \(pair.label): \(v)"
        }.joined(separator: "\n")
    }
}
