import SwiftUI
import AppKit
import SwiftData

@main
struct AgentApp: App {
    @StateObject private var orchestrator: Orchestrator
    let container: ModelContainer

    init() {
        let storeDir = URL(fileURLWithPath: "/Users/viktor/ai_ac/d15/data")
        try? FileManager.default.createDirectory(at: storeDir, withIntermediateDirectories: true)
        let storeURL = storeDir.appendingPathComponent("agent.store")
        let config = ModelConfiguration(url: storeURL)
        do {
            let cont = try ModelContainer(
                for: AgentTaskModel.self, InvariantModel.self, UserProfileModel.self,
                configurations: config
            )
            container = cont
            _orchestrator = StateObject(wrappedValue: Orchestrator(context: ModelContext(cont)))
        } catch {
            fatalError("SwiftData не удалось инициализировать: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(orchestrator)
                .frame(minWidth: 800, minHeight: 560)
                .onAppear { NSApp.activate(ignoringOtherApps: true) }
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified)
        .commands { CommandGroup(replacing: .newItem) {} }
    }
}
