import Foundation

// Launcher for "TG Oxyfire Saver.app". Resolves the engine helper
// relative to this executable so the bundle can live anywhere.
let exe = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
let contents = exe.deletingLastPathComponent().deletingLastPathComponent()
let engine = contents.appendingPathComponent("Helpers/TGSaverEngine.app")
let task = Process()
task.executableURL = URL(fileURLWithPath: "/usr/bin/open")
task.arguments = [engine.path]
do {
    try task.run()
    task.waitUntilExit()
} catch {
    fputs("TG Oxyfire Saver: \(error)\n", stderr)
    exit(1)
}
if task.terminationStatus != 0 {
    exit(task.terminationStatus)
}
