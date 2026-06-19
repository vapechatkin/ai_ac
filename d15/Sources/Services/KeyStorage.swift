import Foundation

enum KeyStorage {
    private static let keyFile = URL(fileURLWithPath: "/Users/viktor/ai_ac/.api_key")

    static func save(_ key: String) {
        try? key.trimmingCharacters(in: .whitespacesAndNewlines)
                .write(to: keyFile, atomically: true, encoding: .utf8)
    }

    static func load() -> String? {
        guard let raw = try? String(contentsOf: keyFile, encoding: .utf8) else { return nil }
        let key = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return key.isEmpty ? nil : key
    }

    static func delete() {
        try? FileManager.default.removeItem(at: keyFile)
    }
}
