import SwiftUI

struct ContentView: View {
    @EnvironmentObject var orchestrator: Orchestrator
    @State private var showMemory = false

    var body: some View {
        Group {
            if !orchestrator.hasProfile() {
                SetupView(onComplete: { orchestrator.isSetupDone = true })
            } else {
                NavigationSplitView {
                    SidebarView(showMemory: $showMemory)
                        .navigationSplitViewColumnWidth(min: 200, ideal: 230, max: 280)
                } detail: {
                    ChatView()
                }
                .sheet(isPresented: $showMemory) {
                    MemoryView()
                }
            }
        }
        .environmentObject(orchestrator)
    }
}
