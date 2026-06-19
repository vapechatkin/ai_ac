import Foundation
import SwiftData

@Model
final class AgentTaskModel {
    @Attribute(.unique) var id: String
    var name: String
    var stageRaw: String
    var expectedActionRaw: String
    var pendingResult: String
    var plan: [String]
    var stepIndex: Int
    var stepNotes: [String]
    var planningResult: String
    var executionResult: String
    var validationResult: String
    var validationPassed: Bool?
    var isCurrent: Bool
    var createdAt: Date
    var updatedAt: Date

    init(name: String) {
        self.id = String(UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(8).lowercased())
        self.name = name
        self.stageRaw = Stage.planning.rawValue
        self.expectedActionRaw = ExpectedAction.inProgress.rawValue
        self.pendingResult = ""
        self.plan = []
        self.stepIndex = 0
        self.stepNotes = []
        self.planningResult = ""
        self.executionResult = ""
        self.validationResult = ""
        self.validationPassed = nil
        self.isCurrent = true
        self.createdAt = Date()
        self.updatedAt = Date()
    }

    var stage: Stage {
        get { Stage(rawValue: stageRaw) ?? .planning }
        set { stageRaw = newValue.rawValue }
    }

    var expectedAction: ExpectedAction {
        get { ExpectedAction(rawValue: expectedActionRaw) ?? .inProgress }
        set { expectedActionRaw = newValue.rawValue }
    }

    func toAgentTask() -> AgentTask {
        let iso = ISO8601DateFormatter()
        return AgentTask(
            id: id,
            name: name,
            stage: stage,
            expectedAction: expectedAction,
            pendingResult: pendingResult,
            plan: plan,
            stepIndex: stepIndex,
            stepNotes: stepNotes,
            stageResults: StageResults(
                planning: planningResult,
                execution: executionResult,
                validation: validationResult,
                validationPassed: validationPassed
            ),
            notes: [],
            createdAt: iso.string(from: createdAt),
            updatedAt: iso.string(from: updatedAt)
        )
    }
}

@Model
final class InvariantModel {
    @Attribute(.unique) var id: String
    var category: String
    var rule: String
    var createdAt: Date

    init(category: String, rule: String) {
        self.id = String(UUID().uuidString.prefix(8).lowercased())
        self.category = category
        self.rule = rule
        self.createdAt = Date()
    }

    func toInvariant() -> Invariant {
        Invariant(id: id, category: category, rule: rule,
                  createdAt: ISO8601DateFormatter().string(from: createdAt))
    }
}

@Model
final class UserProfileModel {
    @Attribute(.unique) var profileId: String
    var name: String
    var occupation: String
    var grade: String
    var stack: String
    var style: String
    var format: String
    var language: String
    var extras: String

    init() {
        self.profileId = "default"
        self.name = ""
        self.occupation = ""
        self.grade = ""
        self.stack = ""
        self.style = ""
        self.format = ""
        self.language = ""
        self.extras = ""
    }
}
