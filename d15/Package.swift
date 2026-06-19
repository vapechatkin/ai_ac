// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AgentApp",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "AgentApp",
            path: "Sources",
            swiftSettings: [.unsafeFlags(["-parse-as-library"])]
        )
    ]
)
