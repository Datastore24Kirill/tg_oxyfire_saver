import Cocoa
import Foundation

let appName = "TG Video Saver"
let support = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/TGVideoSaver")
let logURL = support.appendingPathComponent("app.log")
let iconFlame = support.appendingPathComponent("assets/menubarFlame@2x.png")
let iconColor = support.appendingPathComponent("assets/menubarColor@2x.png")
let iconTemplate = support.appendingPathComponent("assets/menubarFlameTemplate@2x.png")
let iconTemplateAlt = support.appendingPathComponent("assets/menubarTemplate@2x.png")
let autosave = "TGVideoSaver"

func log(_ msg: String) {
    let line = (msg + "\n").data(using: .utf8)!
    if FileManager.default.fileExists(atPath: logURL.path),
       let h = try? FileHandle(forWritingTo: logURL)
    {
        defer { try? h.close() }
        h.seekToEndOfFile()
        h.write(line)
    } else {
        try? line.write(to: logURL)
    }
}

func runDefaults(_ args: [String]) {
    let t = Process()
    t.executableURL = URL(fileURLWithPath: "/usr/bin/defaults")
    t.arguments = args
    t.standardOutput = FileHandle.nullDevice
    t.standardError = FileHandle.nullDevice
    try? t.run()
    t.waitUntilExit()
}

func forceVisiblePrefs() {
    let bid = Bundle.main.bundleIdentifier ?? "com.oxyfire.tgvideosaver"
    for domain in [bid, "com.apple.controlcenter"] {
        for key in [
            "NSStatusItem Visible \(autosave)",
            "NSStatusItem VisibleCC \(autosave)",
        ] {
            runDefaults(["write", domain, key, "-bool", "true"])
        }
        runDefaults([
            "write", domain,
            "NSStatusItem Preferred Position \(autosave)",
            "-float", "480",
        ])
    }
}

func apiGet(_ base: String, _ path: String) -> [String: Any]? {
    guard let url = URL(string: base + path) else { return nil }
    var req = URLRequest(url: url, timeoutInterval: 2)
    req.httpMethod = "GET"
    let sem = DispatchSemaphore(value: 0)
    var result: [String: Any]?
    URLSession.shared.dataTask(with: req) { data, _, _ in
        defer { sem.signal() }
        if let data,
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        {
            result = obj
        }
    }.resume()
    _ = sem.wait(timeout: .now() + 2.5)
    return result
}

func apiPost(_ base: String, _ path: String, _ body: [String: Any]) {
    guard let url = URL(string: base + path),
          let data = try? JSONSerialization.data(withJSONObject: body)
    else { return }
    var req = URLRequest(url: url, timeoutInterval: 3)
    req.httpMethod = "POST"
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.httpBody = data
    let sem = DispatchSemaphore(value: 0)
    URLSession.shared.dataTask(with: req) { _, _, _ in sem.signal() }.resume()
    _ = sem.wait(timeout: .now() + 3)
}

final class MenuApp: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    var pauseItem: NSMenuItem!
    var port: Int = 8765
    var base: String { "http://127.0.0.1:\(port)" }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        forceVisiblePrefs()

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.autosaveName = autosave
        statusItem.isVisible = true

        if let btn = statusItem.button {
            // Сгенерированное пламя (цветное), иначе template
            var loaded = false
            for (url, asTemplate) in [
                (iconFlame, false),
                (iconColor, false),
                (iconTemplate, true),
                (iconTemplateAlt, true),
            ] as [(URL, Bool)] {
                if let img = NSImage(contentsOf: url) {
                    img.isTemplate = asTemplate
                    img.size = NSSize(width: 18, height: 18)
                    btn.image = img
                    btn.imagePosition = .imageOnly
                    loaded = true
                    break
                }
            }
            if !loaded, let sym = NSImage(
                systemSymbolName: "flame.fill",
                accessibilityDescription: nil
            ) {
                sym.isTemplate = true
                btn.image = sym
                btn.imagePosition = .imageOnly
            }
            // Текст только как запасной якорь, если картинки нет
            btn.title = loaded ? "" : "TG"
            btn.toolTip = appName
        }

        let menu = NSMenu()
        pauseItem = NSMenuItem(
            title: "Пауза очереди",
            action: #selector(togglePause),
            keyEquivalent: ""
        )
        pauseItem.target = self
        menu.addItem(pauseItem)

        for (title, sel) in [
            ("Открыть окно", #selector(openWindow)),
            ("Открыть папку", #selector(openFolder)),
            ("О программе…", #selector(showAbout)),
            ("Настройки Menu Bar…", #selector(openSettings)),
        ] as [(String, Selector)] {
            let it = NSMenuItem(title: title, action: sel, keyEquivalent: "")
            it.target = self
            menu.addItem(it)
        }
        menu.addItem(NSMenuItem.separator())
        let quit = NSMenuItem(title: "Выход", action: #selector(quitAll), keyEquivalent: "")
        quit.target = self
        menu.addItem(quit)
        statusItem.menu = menu

        log("native_menu ONCE id=\(Bundle.main.bundleIdentifier ?? "?") port=\(port)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            self?.verifyVisible()
        }
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            self?.tick()
        }
    }

    func verifyVisible() {
        guard let btn = statusItem.button, let win = btn.window else {
            log("native_menu verify win=None")
            return
        }
        let f = win.frame
        let ok = win.screen != nil && f.height >= 20 && f.origin.y > 200
        log(
            "native_menu verify screen=\(win.screen != nil) "
                + "win=(\(Int(f.origin.x)),\(Int(f.origin.y)),\(Int(f.width))x\(Int(f.height))) ok=\(ok)"
        )
        if !ok {
            forceVisiblePrefs()
            statusItem.isVisible = true
            if let url = URL(string: "x-apple.systempreferences:com.apple.MenuBarSettings") {
                NSWorkspace.shared.open(url)
            }
        }
    }

    @objc func tick() {
        guard let st = apiGet(base, "/api/state") else { return }
        let paused = st["paused"] as? Bool ?? false
        pauseItem.title = paused ? "Продолжить очередь" : "Пауза очереди"
        let stats = st["stats"] as? [String: Any] ?? [:]
        let active = (stats["active"] as? Int)
            ?? Int(stats["active"] as? Double ?? 0)
        let queued = (stats["queued"] as? Int)
            ?? Int(stats["queued"] as? Double ?? 0)
        let ready = st["ready"] as? Bool ?? false
        var title = ""
        if !ready { title = "…" }
        else if active > 0 { title = "↓\(active)" }
        else if queued > 0 { title = "·\(queued)" }
        if let btn = statusItem.button {
            btn.title = title
            btn.imagePosition = title.isEmpty ? .imageOnly : .imageLeft
        }
        statusItem.isVisible = true
    }

    @objc func openWindow() {
        let helpers = [
            "/Applications/TG Oxyfire Saver.app/Contents/Helpers/TGSaverWindow.app",
            "/Applications/TG Video Saver.app/Contents/Helpers/TGSaverWindow.app",
            NSString(string: "~/Desktop/TG Video Saver.app/Contents/Helpers/TGSaverWindow.app").expandingTildeInPath,
            NSString(string: "~/Desktop/TG Oxyfire Saver.app/Contents/Helpers/TGSaverWindow.app").expandingTildeInPath,
            NSString(string: "~/Applications/TG Oxyfire Saver.app/Contents/Helpers/TGSaverWindow.app").expandingTildeInPath,
        ]
        let path = helpers.first { FileManager.default.fileExists(atPath: $0) } ?? helpers[0]
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = [path, "--args", "\(port)"]
        try? p.run()
    }

    @objc func togglePause() {
        guard let st = apiGet(base, "/api/state") else { return }
        let paused = st["paused"] as? Bool ?? false
        apiPost(base, "/api/pause", ["paused": !paused])
    }

    @objc func openFolder() {
        apiPost(base, "/api/open_folder", [:])
    }

    @objc func openSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.MenuBarSettings") {
            NSWorkspace.shared.open(url)
        }
    }

    @objc func showAbout() {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = .center
        let base: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11),
            .foregroundColor: NSColor.labelColor,
            .paragraphStyle: paragraph,
        ]
        let credits = NSMutableAttributedString(
            string: "Автор: Ковыршин Кирилл\n© 2016 Ковыршин Кирилл\n\n",
            attributes: base
        )
        let links = [
            "https://3dwolf.ru",
            "https://datastore24.ru",
            "https://myfabric.ru",
        ]
        for (i, url) in links.enumerated() {
            let label = url.replacingOccurrences(of: "https://", with: "")
                + (i < links.count - 1 ? "\n" : "")
            var attrs = base
            attrs[.link] = URL(string: url) as Any
            attrs[.foregroundColor] = NSColor.linkColor
            credits.append(NSAttributedString(string: label, attributes: attrs))
        }
        var opts: [NSApplication.AboutPanelOptionKey: Any] = [
            .applicationName: "TG Oxyfire Saver",
            .applicationVersion: "2.6.0",
            .version: "2.6.0",
            .credits: credits,
        ]
        let iconPath = support.appendingPathComponent("assets/icon.png").path
        if let img = NSImage(contentsOfFile: iconPath) {
            opts[.applicationIcon] = img
        }
        NSApp.orderFrontStandardAboutPanel(options: opts)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func quitAll() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        p.arguments = ["-f", "Application Support/TGVideoSaver/app_main.py"]
        try? p.run()
        p.waitUntilExit()
        NSApp.terminate(nil)
    }
}

let args = CommandLine.arguments
var port = 8765
if args.count > 1, let p = Int(args[1]) {
    port = p
} else {
    let portFile = support.appendingPathComponent(".api_port")
    if let s = try? String(contentsOf: portFile, encoding: .utf8),
       let p = Int(s.trimmingCharacters(in: .whitespacesAndNewlines))
    {
        port = p
    }
}

let base = "http://127.0.0.1:\(port)"
for _ in 0 ..< 40 {
    if apiGet(base, "/api/health") != nil { break }
    Thread.sleep(forTimeInterval: 0.25)
}

let app = NSApplication.shared
let delegate = MenuApp()
delegate.port = port
app.delegate = delegate
app.run()
