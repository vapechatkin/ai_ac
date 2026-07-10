import Foundation

// Ollama /api/chat response shapes
private struct OllamaResponse: Decodable {
    struct Message: Decodable { let content: String }
    let message: Message
}

class OllamaClient: LLMClient {
    let model: String
    private let baseURL: URL

    init(model: String = "qwen2.5:0.5b", baseURL: String = "http://localhost:11434") {
        self.model   = model
        self.baseURL = URL(string: baseURL)!
    }

    func createMessage(
        system:     String,
        messages:   [[String: Any]],
        tools:      [[String: Any]] = [],
        toolChoice: [String: Any]?  = nil,
        maxTokens:  Int             = 4096
    ) async throws -> AnthropicResponse {
        // Build message list: system + history
        var ollamaMessages: [[String: Any]] = []
        if !system.isEmpty {
            ollamaMessages.append(["role": "system", "content": system])
        }
        for m in messages {
            let role = m["role"] as? String ?? "user"
            // content may be a String or [[String:Any]] (tool results) — flatten to text
            let text: String
            if let s = m["content"] as? String {
                text = s
            } else if let arr = m["content"] as? [[String: Any]] {
                text = arr.compactMap { $0["content"] as? String }.joined(separator: "\n")
            } else {
                continue
            }
            ollamaMessages.append(["role": role, "content": text])
        }

        let body: [String: Any] = [
            "model":    model,
            "messages": ollamaMessages,
            "stream":   false,
            "options":  ["num_predict": maxTokens]
        ]

        var req = URLRequest(url: baseURL.appendingPathComponent("/api/chat"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        req.timeoutInterval = 120

        let (data, resp) = try await URLSession.shared.data(for: req)
        if let http = resp as? HTTPURLResponse, http.statusCode != 200 {
            throw APIError(message: "Ollama HTTP \(http.statusCode): \(String(data: data, encoding: .utf8) ?? "")")
        }
        let ollamaResp = try JSONDecoder().decode(OllamaResponse.self, from: data)
        let block = ContentBlock(type: "text", text: ollamaResp.message.content,
                                 id: nil, name: nil, input: nil)
        return AnthropicResponse(content: [block], stopReason: "end_turn")
    }

    func userMsg(_ text: String) -> [String: Any] {
        ["role": "user", "content": text]
    }

    func assistantMsg(_ blocks: [ContentBlock]) -> [String: Any] {
        let text = blocks.compactMap(\.text).joined(separator: "\n")
        return ["role": "assistant", "content": text]
    }

    func toolResultMsg(toolUseId: String, result: String) -> [String: Any] {
        ["role": "user", "content": result]
    }
}
