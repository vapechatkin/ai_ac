import Foundation

// MARK: - Stage machine

enum Stage: String, Codable, CaseIterable {
    case planning, execution, validation, done
}

enum ExpectedAction: String, Codable {
    case inProgress    = "in_progress"
    case awaitingConfirm = "awaiting_confirm"
    case done          = "done"
}

// MARK: - Workflow / Task

struct TaskNote: Codable {
    var time: String
    var text: String
}

struct StageResults: Codable {
    var planning:         String  = ""
    var execution:        String  = ""
    var validation:       String  = ""
    var validationPassed: Bool?   = nil

    enum CodingKeys: String, CodingKey {
        case planning, execution, validation
        case validationPassed = "validation_passed"
    }
}

// Renamed to avoid clash with Swift.Task
struct AgentTask: Codable, Identifiable {
    var id:             String
    var name:           String
    var stage:          Stage
    var expectedAction: ExpectedAction
    var pendingResult:  String        = ""
    var plan:           [String]      = []
    var stepIndex:      Int           = 0
    var stepNotes:      [String]      = []
    var stageResults:   StageResults  = StageResults()
    var notes:          [TaskNote]    = []
    var createdAt:      String
    var updatedAt:      String

    enum CodingKeys: String, CodingKey {
        case id, name, stage, plan, notes
        case expectedAction  = "expected_action"
        case pendingResult   = "pending_result"
        case stepIndex       = "step_index"
        case stepNotes       = "step_notes"
        case stageResults    = "stage_results"
        case createdAt       = "created_at"
        case updatedAt       = "updated_at"
    }
}

struct WorkflowFile: Codable {
    var current: String      = ""
    var tasks:   [AgentTask] = []
}

// MARK: - Invariants

struct Invariant: Codable, Identifiable {
    var id:        String
    var category:  String
    var rule:      String
    var createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, category, rule
        case createdAt = "created_at"
    }
}

struct InvariantsFile: Codable {
    var invariants: [Invariant] = []
}

// MARK: - Chat UI

enum MsgRole { case user, assistant }

struct ChatMessage: Identifiable {
    let id   = UUID()
    let role:    MsgRole
    let content: String
}

// MARK: - Anthropic API response

struct JSONValue: Decodable {
    let rawValue: Any

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let d = try? c.decode([String: JSONValue].self) {
            rawValue = d.mapValues(\.rawValue)
        } else if let a = try? c.decode([JSONValue].self) {
            rawValue = a.map(\.rawValue)
        } else if let s = try? c.decode(String.self)  { rawValue = s }
        else if let i = try? c.decode(Int.self)        { rawValue = i }
        else if let f = try? c.decode(Double.self)     { rawValue = f }
        else if let b = try? c.decode(Bool.self)       { rawValue = b }
        else                                            { rawValue = NSNull() }
    }
}

struct ContentBlock: Decodable {
    var type:  String
    var text:  String?
    var id:    String?
    var name:  String?
    var input: JSONValue?       // tool_use input — decoded as JSONValue → [String: Any]

    var inputDict: [String: Any] {
        (input?.rawValue as? [String: Any]) ?? [:]
    }
}

struct AnthropicResponse: Decodable {
    var content:    [ContentBlock]
    var stopReason: String?

    enum CodingKeys: String, CodingKey {
        case content
        case stopReason = "stop_reason"
    }
}
