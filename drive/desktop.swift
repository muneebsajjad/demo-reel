// desktop: drives native macOS apps for a desktop take (see drive/take.mjs, `config.desktop`).
//
//   desktop            reads one JSON command per line on stdin, answers one JSON line each
//   desktop --check    exit 0 if this terminal may send input (Accessibility), 2 if not
//
// Commands ({"op": …}):
//   frames   {apps:[bundle prefix…]}           -> {windows:[{app,pid,title,x,y,width,height}]} global points
//   launch   {app, path?, args?, env?}          -> starts (or reuses) an app and waits for a window
//   activate {app}                              -> brings the app forward
//   running  {app}                              -> {running, pid, path}
//   quit     {app}                              -> asks the app to quit (forces it after 5 s)
//   place    {app, title?, index?, x, y, width, height} -> moves and sizes a window (Accessibility);
//            give the title when the app has panels (they count as windows too)
//   press    {app, name}                        -> press that control (no pointer; for clean-up)
//   find     {app, name}                        -> the frame of the control with that title or label
//   screen   {x, y}                             -> the frame of the display holding that point
//   backdrop {at:[x,y], colors:[top,bottom], show?} -> a plain window behind every app, so the take
//            shows a clean surface instead of the person's desktop (recorded by passing --pid)
//   modifier {key, down}                        -> press or release a modifier (rightOption, …) as a
//            real flagsChanged event, the way a push-to-talk key arrives
//   key      {code, flags?}                     -> press and release a key (virtual key code)
//   type     {text, cps?}                       -> type text at a human rhythm
//   move     {x, y, ms?}                        -> glide the real cursor, eased, on a slight curve
//   click    {x, y, ms?}                        -> glide there, then click
// Errors come back as {"error": "…"}. Positions are global screen points, top-left origin.
import AppKit
import ApplicationServices
import Foundation

setlinebuf(stdout)

func reply(_ obj: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}

if CommandLine.arguments.contains("--check") {
    let ok = AXIsProcessTrusted()
    reply(["accessibility": ok])
    exit(ok ? 0 : 2)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)          // no Dock icon, never takes focus from the apps it drives

// MARK: - input

let source = CGEventSource(stateID: .hidSystemState)
let MODIFIERS: [String: (code: CGKeyCode, flags: UInt64)] = [
    // device-dependent bits tell left from right, as a real keyboard reports them
    "rightOption": (61, CGEventFlags.maskAlternate.rawValue | 0x40),
    "leftOption": (58, CGEventFlags.maskAlternate.rawValue | 0x20),
    "rightCommand": (54, CGEventFlags.maskCommand.rawValue | 0x10),
    "rightControl": (62, CGEventFlags.maskControl.rawValue | 0x2000),
    "rightShift": (60, CGEventFlags.maskShift.rawValue | 0x4),
]

func modifier(_ name: String, down: Bool) throws {
    guard let m = MODIFIERS[name] else { throw Fail("unknown modifier \(name)") }
    guard let e = CGEvent(keyboardEventSource: source, virtualKey: m.code, keyDown: down) else { throw Fail("no event") }
    e.type = .flagsChanged
    e.flags = CGEventFlags(rawValue: down ? m.flags | 0x100 : 0x100)   // 0x100: no other device bits
    e.post(tap: .cghidEventTap)
}

func key(_ code: CGKeyCode, flags: UInt64 = 0) {
    for down in [true, false] {
        let e = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: down)!
        e.flags = CGEventFlags(rawValue: flags)
        e.post(tap: .cghidEventTap)
        usleep(30_000)
    }
}

func type(_ text: String, cps: Double) {
    for ch in text {
        let units = Array(String(ch).utf16)
        for down in [true, false] {
            let e = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: down)!
            e.keyboardSetUnicodeString(stringLength: units.count, unicodeString: units)
            e.post(tap: .cghidEventTap)
        }
        usleep(UInt32(1_000_000 / cps * Double.random(in: 0.7...1.3)))
    }
}

func cursor() -> CGPoint { CGEvent(source: nil)?.location ?? .zero }

func glide(to: CGPoint, ms: Double) {
    let from = cursor(), n = max(2, Int(ms / 16))
    let bow = CGPoint(x: (to.y - from.y) * 0.08, y: (from.x - to.x) * 0.08)
    for i in 1...n {
        let t = Double(i) / Double(n)
        let u = t < 0.5 ? 4 * t * t * t : 1 - pow(-2 * t + 2, 3) / 2
        let b = sin(Double.pi * t)
        let p = CGPoint(x: from.x + (to.x - from.x) * u + bow.x * b, y: from.y + (to.y - from.y) * u + bow.y * b)
        CGEvent(mouseEventSource: source, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)?
            .post(tap: .cghidEventTap)
        usleep(16_000)
    }
}

func click(at p: CGPoint) {
    for type in [CGEventType.leftMouseDown, .leftMouseUp] {
        CGEvent(mouseEventSource: source, mouseType: type, mouseCursorPosition: p, mouseButton: .left)?
            .post(tap: .cghidEventTap)
        usleep(70_000)
    }
}

// MARK: - windows

struct Fail: Error { let message: String; init(_ m: String) { message = m } }

func running(_ prefix: String) -> NSRunningApplication? {
    NSWorkspace.shared.runningApplications.first { ($0.bundleIdentifier ?? "").hasPrefix(prefix) }
}

func frames(_ apps: [String]) -> [[String: Any]] {
    let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
        as? [[String: Any]] ?? []
    var out: [[String: Any]] = []
    for w in list {
        guard let pid = w[kCGWindowOwnerPID as String] as? pid_t,
              let bundle = NSRunningApplication(processIdentifier: pid)?.bundleIdentifier,
              apps.contains(where: { bundle.hasPrefix($0) }),
              let b = w[kCGWindowBounds as String] as? [String: CGFloat] else { continue }
        out.append(["app": bundle, "pid": pid, "title": w[kCGWindowName as String] as? String ?? "",
                    "layer": w[kCGWindowLayer as String] as? Int ?? 0,
                    "x": b["X"] ?? 0, "y": b["Y"] ?? 0, "width": b["Width"] ?? 0, "height": b["Height"] ?? 0])
    }
    return out
}

func axWindows(_ pid: pid_t) -> [AXUIElement] {
    var value: CFTypeRef?
    AXUIElementCopyAttributeValue(AXUIElementCreateApplication(pid), kAXWindowsAttribute as CFString, &value)
    return value as? [AXUIElement] ?? []
}

func axTitle(_ w: AXUIElement) -> String {
    var v: CFTypeRef?
    AXUIElementCopyAttributeValue(w, kAXTitleAttribute as CFString, &v)
    return v as? String ?? ""
}

// The frame of the first element (button, link, text) in an app whose title, description or value
// is `name`: how a scenario clicks a control without knowing its pixels. Web views expose theirs too.
func find(_ prefix: String, name: String) throws -> CGRect { try findElement(prefix, name: name).1 }

func findElement(_ prefix: String, name: String) throws -> (AXUIElement, CGRect) {
    guard let a = running(prefix) else { throw Fail("\(prefix) is not running") }
    func attr(_ e: AXUIElement, _ k: String) -> CFTypeRef? {
        var v: CFTypeRef?
        AXUIElementCopyAttributeValue(e, k as CFString, &v)
        return v
    }
    func frame(_ e: AXUIElement) -> CGRect? {
        guard let p = attr(e, kAXPositionAttribute), let z = attr(e, kAXSizeAttribute) else { return nil }
        var o = CGPoint.zero, sz = CGSize.zero
        AXValueGetValue(p as! AXValue, .cgPoint, &o)
        AXValueGetValue(z as! AXValue, .cgSize, &sz)
        return CGRect(origin: o, size: sz)
    }
    // web views (WKWebView, Electron, Tauri) build their accessibility tree only when asked to
    let appEl = AXUIElementCreateApplication(a.processIdentifier)
    for k in ["AXManualAccessibility", "AXEnhancedUserInterface"] {
        AXUIElementSetAttributeValue(appEl, k as CFString, kCFBooleanTrue)
    }
    usleep(300_000)
    var queue: [(AXUIElement, Int)] = axWindows(a.processIdentifier).map { ($0, 0) }
    while !queue.isEmpty {
        let (e, depth) = queue.removeFirst()
        let names = [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute].compactMap { attr(e, $0) as? String }
        let role = attr(e, kAXRoleAttribute) as? String ?? ""
        if names.contains(name), role != "AXStaticText" || queue.isEmpty, let f = frame(e), f.width > 0 { return (e, f) }
        if depth < 30, let kids = attr(e, kAXChildrenAttribute) as? [AXUIElement] { queue += kids.map { ($0, depth + 1) } }
    }
    throw Fail("no element named \"\(name)\" in \(prefix)")
}

func place(_ prefix: String, index: Int, title: String?, _ r: CGRect) throws {
    guard let a = running(prefix) else { throw Fail("\(prefix) is not running") }
    var wins = axWindows(a.processIdentifier)
    if let title { wins = wins.filter { axTitle($0) == title } }      // an app's panels are windows too
    guard index < wins.count else {
        throw Fail("\(prefix) has no accessible window\(title.map { " titled \"\($0)\"" } ?? "") (\(wins.count) found)")
    }
    var origin = r.origin, size = r.size
    let w = wins[index]
    // position, size, then position again: a window moved to another display is first clamped to it
    for (attr, value) in [(kAXPositionAttribute, AXValueCreate(.cgPoint, &origin)!), (kAXSizeAttribute, AXValueCreate(.cgSize, &size)!),
                          (kAXPositionAttribute, AXValueCreate(.cgPoint, &origin)!)] {
        let err = AXUIElementSetAttributeValue(w, attr as CFString, value)
        if err != .success { throw Fail("could not set \(attr) of \(prefix)'s window (AXError \(err.rawValue))") }
    }
}

func launch(_ prefix: String, path: String?, args: [String], env: [String: String]) throws {
    if running(prefix) == nil {
        let p = Process()
        if let path {
            // run the binary inside the bundle directly, so `env` reaches it
            p.executableURL = URL(fileURLWithPath: path)
            p.arguments = args
            p.environment = ProcessInfo.processInfo.environment.merging(env) { $1 }
        } else {
            p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
            p.arguments = ["-b", prefix] + (args.isEmpty ? [] : ["--args"] + args)
        }
        try p.run()
    }
    for _ in 0..<150 {
        if !frames([prefix]).filter({ ($0["layer"] as? Int) == 0 }).isEmpty { return }
        usleep(100_000)
    }
    throw Fail("\(prefix) opened no window")
}

// A plain gradient window just above the desktop picture and below every app.
var backdrop: NSWindow?
// The display holding a point in global (top-left origin) coordinates.
func displayBounds(_ p: CGPoint) -> CGRect {
    var id: CGDirectDisplayID = 0, n: UInt32 = 0
    CGGetDisplaysWithPoint(p, 1, &id, &n)
    return CGDisplayBounds(n > 0 ? id : CGMainDisplayID())
}

func showBackdrop(at p: CGPoint, colors: [String], show: Bool) {
    backdrop?.orderOut(nil)
    backdrop = nil
    guard show else { return }
    let b = displayBounds(p)
    let primary = CGDisplayBounds(CGMainDisplayID()).height
    let nsFrame = CGRect(x: b.minX, y: primary - b.maxY, width: b.width, height: b.height)   // AppKit is bottom-left
    let screen = NSScreen.screens.first { $0.frame == nsFrame } ?? NSScreen.main!
    let w = NSWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false, screen: screen)
    w.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.desktopWindow)) + 1)
    w.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
    w.ignoresMouseEvents = true
    let v = NSView(frame: screen.frame)
    v.wantsLayer = true
    let g = CAGradientLayer()
    g.frame = v.bounds
    g.colors = colors.map { NSColor(hex: $0).cgColor }
    g.startPoint = CGPoint(x: 0.5, y: 1)
    g.endPoint = CGPoint(x: 0.5, y: 0)
    v.layer = g
    w.contentView = v
    w.setFrame(screen.frame, display: true)
    w.orderFront(nil)
    backdrop = w
}

extension NSColor {
    convenience init(hex: String) {
        let v = UInt32(hex.trimmingCharacters(in: CharacterSet(charactersIn: "#")), radix: 16) ?? 0
        self.init(srgbRed: CGFloat(v >> 16 & 0xff) / 255, green: CGFloat(v >> 8 & 0xff) / 255,
                  blue: CGFloat(v & 0xff) / 255, alpha: 1)
    }
}

// MARK: - command loop

func handle(_ c: [String: Any]) throws -> [String: Any] {
    let num = { (k: String) in CGFloat((c[k] as? NSNumber)?.doubleValue ?? 0) }
    switch c["op"] as? String ?? "" {
    case "frames": return ["windows": frames(c["apps"] as? [String] ?? [])]
    case "launch":
        try launch(c["app"] as! String, path: c["path"] as? String, args: c["args"] as? [String] ?? [],
                   env: c["env"] as? [String: String] ?? [:])
    case "running":
        let a = running(c["app"] as! String)
        return ["running": a != nil, "pid": a?.processIdentifier ?? 0, "path": a?.bundleURL?.path ?? ""]
    case "quit":
        if let a = running(c["app"] as! String) {
            a.terminate()
            for _ in 0..<50 where !a.isTerminated { usleep(100_000) }
            if !a.isTerminated { a.forceTerminate() }
        }
    case "activate":
        guard let a = running(c["app"] as! String) else { throw Fail("not running") }
        a.activate()
    case "place":
        try place(c["app"] as! String, index: c["index"] as? Int ?? 0, title: c["title"] as? String,
                  CGRect(x: num("x"), y: num("y"), width: num("width"), height: num("height")))
    case "backdrop":
        let at = (c["at"] as? [NSNumber])?.map { CGFloat($0.doubleValue) } ?? [0, 0]
        let run = { showBackdrop(at: CGPoint(x: at[0], y: at[1]), colors: c["colors"] as? [String] ?? ["#ffffff", "#ffffff"],
                                 show: c["show"] as? Bool ?? true) }
        DispatchQueue.main.sync(execute: run)
        return ["pid": getpid()]
    case "modifier": try modifier(c["key"] as! String, down: c["down"] as? Bool ?? true)
    case "key": key(CGKeyCode(num("code")), flags: UInt64(num("flags")))
    case "type": type(c["text"] as? String ?? "", cps: Double(num("cps")) > 0 ? Double(num("cps")) : 14)
    case "move": glide(to: CGPoint(x: num("x"), y: num("y")), ms: Double(num("ms")) > 0 ? Double(num("ms")) : 600)
    case "click":
        let p = CGPoint(x: num("x"), y: num("y"))
        glide(to: p, ms: Double(num("ms")) > 0 ? Double(num("ms")) : 600)
        usleep(90_000)
        click(at: p)
    case "cursor": let p = cursor(); return ["x": p.x, "y": p.y]
    case "press":                                    // press a control by its label, without the pointer
        let (e, _) = try findElement(c["app"] as! String, name: c["name"] as! String)
        let err = AXUIElementPerformAction(e, kAXPressAction as CFString)
        if err != .success { throw Fail("could not press \(c["name"]!) (AXError \(err.rawValue))") }
    case "find":
        let f = try find(c["app"] as! String, name: c["name"] as! String)
        return ["x": f.minX, "y": f.minY, "width": f.width, "height": f.height]
    case "screen":
        let b = displayBounds(CGPoint(x: num("x"), y: num("y")))
        return ["x": b.minX, "y": b.minY, "width": b.width, "height": b.height]
    case let op: throw Fail("unknown op \(op)")
    }
    return ["ok": true]
}

Thread.detachNewThread {
    while let line = readLine() {
        guard let data = line.data(using: .utf8),
              let c = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            reply(["error": "not JSON: \(line)"]); continue
        }
        do { reply(try handle(c)) } catch let f as Fail { reply(["error": f.message]) } catch { reply(["error": "\(error)"]) }
    }
    exit(0)
}
app.run()
