import Foundation

protocol LLMClient {
    func createMessage(
        system:     String,
        messages:   [[String: Any]],
        tools:      [[String: Any]],
        toolChoice: [String: Any]?,
        maxTokens:  Int
    ) async throws -> AnthropicResponse

    func userMsg(_ text: String) -> [String: Any]
    func assistantMsg(_ blocks: [ContentBlock]) -> [String: Any]
    func toolResultMsg(toolUseId: String, result: String) -> [String: Any]
}

extension LLMClient {
    func createMessage(
        system:     String,
        messages:   [[String: Any]],
        tools:      [[String: Any]] = [],
        toolChoice: [String: Any]?  = nil,
        maxTokens:  Int             = 4096
    ) async throws -> AnthropicResponse {
        try await createMessage(system: system, messages: messages,
                                tools: tools, toolChoice: toolChoice, maxTokens: maxTokens)
    }
}
