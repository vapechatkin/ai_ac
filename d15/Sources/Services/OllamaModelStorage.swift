import Foundation

enum OllamaModelStorage {
    private static let file = URL(fileURLWithPath: "/Users/viktor/ai_ac/.ollama_model")

    static func save(_ model: String) {
        try? model.write(to: file, atomically: true, encoding: .utf8)
    }

    static func load() -> String {
        (try? String(contentsOf: file, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines))
            .flatMap { $0.isEmpty ? nil : $0 } ?? "qwen2.5:0.5b"
    }
}
