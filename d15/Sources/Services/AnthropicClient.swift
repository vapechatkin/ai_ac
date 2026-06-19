import Foundation

struct APIError: Error, LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

class AnthropicClient {
    let apiKey: String
    let model  = "claude-haiku-4-5-20251001"
    private let endpoint = URL(string: "https://api.anthropic.com/v1/messages")!

    init(apiKey: String) { self.apiKey = apiKey }

    func createMessage(
        system:    String,
        messages:  [[String: Any]],
        tools:     [[String: Any]] = [],
        toolChoice: [String: Any]? = nil,
        maxTokens: Int = 4096
    ) async throws -> AnthropicResponse {
        var body: [String: Any] = [
            "model":      model,
            "max_tokens": maxTokens,
            "system":     system,
            "messages":   messages
        ]
        if !tools.isEmpty      { body["tools"]       = tools }
        if let tc = toolChoice { body["tool_choice"] = tc    }

        var req = URLRequest(url: endpoint)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(apiKey,             forHTTPHeaderField: "x-api-key")
        req.setValue("2023-06-01",       forHTTPHeaderField: "anthropic-version")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, resp) = try await URLSession.shared.data(for: req)
        if let http = resp as? HTTPURLResponse, http.statusCode != 200 {
            throw APIError(message: "HTTP \(http.statusCode): \(String(data: data, encoding: .utf8) ?? "")")
        }
        return try JSONDecoder().decode(AnthropicResponse.self, from: data)
    }

    // MARK: - Message builders

    func userMsg(_ text: String) -> [String: Any] {
        ["role": "user", "content": text]
    }

    func assistantMsg(_ blocks: [ContentBlock]) -> [String: Any] {
        ["role": "assistant", "content": blocks.map { blockToDict($0) }]
    }

    func toolResultMsg(toolUseId: String, result: String) -> [String: Any] {
        ["role": "user", "content": [
            ["type": "tool_result", "tool_use_id": toolUseId, "content": result]
        ]]
    }

    private func blockToDict(_ b: ContentBlock) -> [String: Any] {
        var d: [String: Any] = ["type": b.type]
        if let t = b.text  { d["text"]  = t }
        if let i = b.id    { d["id"]    = i }
        if let n = b.name  { d["name"]  = n }
        if let inp = b.input { d["input"] = inp.rawValue }
        return d
    }
}
