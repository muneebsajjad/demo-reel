// record: capture one app's windows and that app's sound, nothing else on the screen or speakers.
//
//   record --app <bundle id prefix> --out take.mov [--seconds 120] [--no-audio] [--cursor]
//   record --check-permission
//
// Stops when <out>.stop appears (touch it from your driver), or after --seconds.
// Prints one JSON line per event on stdout, line-buffered:
//   {"event":"started", "display":{...}, "window":{...}, "scale":2}   when the first frame is recorded
//   {"event":"saved", "path":"..."}
//
// Video: the display holding the app's largest window, with every other app excluded, so a window
// that covers it does not appear. Audio: everything except the excluded apps. Chrome plays sound from
// helper processes that are not listed as applications, so excluding the others (rather than
// including only the app) is what keeps its sound.
import AppKit
import AVFoundation
import Foundation
import ScreenCaptureKit

setlinebuf(stdout)
_ = NSApplication.shared          // ScreenCaptureKit needs the window server connection initialised
_ = CGMainDisplayID()

func emit(_ obj: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}
func fail(_ msg: String) -> Never { emit(["event": "error", "message": msg]); exit(1) }

// record --check-permission: exit 0 if this terminal may record the screen, 2 if not
if CommandLine.arguments.contains("--check-permission") {
    let ok = CGPreflightScreenCaptureAccess()
    emit(["event": "permission", "screen": ok])
    exit(ok ? 0 : 2)
}

var app = "com.google.chrome.for.testing", outPath = "take.mov", seconds = 120.0
var audio = true, cursor = false
var it = CommandLine.arguments.dropFirst().makeIterator()
while let a = it.next() {
    switch a {
    case "--app": app = it.next() ?? app
    case "--out": outPath = it.next() ?? outPath
    case "--seconds": seconds = Double(it.next() ?? "") ?? seconds
    case "--no-audio": audio = false
    case "--cursor": cursor = true
    default: fail("unknown argument \(a)")
    }
}
let out = URL(fileURLWithPath: outPath)
try? FileManager.default.removeItem(at: out)
let stopFile = out.path + ".stop"
try? FileManager.default.removeItem(atPath: stopFile)

let content: SCShareableContent
do { content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true) }
catch { fail("screen capture not permitted: give your terminal Screen & System Audio Recording permission (\(error))") }

let wins = content.windows.filter {
    ($0.owningApplication?.bundleIdentifier ?? "").hasPrefix(app) && $0.windowLayer == 0 && $0.frame.width > 200
}
guard let win = wins.max(by: { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height }) else {
    fail("no on-screen window for \(app)")
}
guard let display = content.displays.first(where: { $0.frame.contains(CGPoint(x: win.frame.midX, y: win.frame.midY)) })
        ?? content.displays.first(where: { $0.frame.intersects(win.frame) }) else { fail("no display for window") }

let others = content.applications.filter { !$0.bundleIdentifier.hasPrefix(app) }
let filter = SCContentFilter(display: display, excludingApplications: others, exceptingWindows: [])
let scale = Double(filter.pointPixelScale)
let cfg = SCStreamConfiguration()
cfg.width = Int(Double(display.width) * scale)
cfg.height = Int(Double(display.height) * scale)
cfg.minimumFrameInterval = CMTime(value: 1, timescale: 60)
cfg.showsCursor = cursor
cfg.capturesAudio = audio
cfg.sampleRate = 48000
cfg.channelCount = 2
cfg.excludesCurrentProcessAudio = true

let f = win.frame
let info: [String: Any] = [
    "event": "started", "scale": scale,
    "display": ["id": display.displayID, "width": display.width, "height": display.height],
    // the window in display points; multiply by scale for pixels in the recording
    "window": ["x": f.minX - display.frame.minX, "y": f.minY - display.frame.minY, "width": f.width, "height": f.height],
]

final class Delegate: NSObject, SCRecordingOutputDelegate, SCStreamDelegate {
    let info: [String: Any]
    init(_ info: [String: Any]) { self.info = info }
    func recordingOutputDidStartRecording(_ r: SCRecordingOutput) { emit(info) }
    func recordingOutput(_ r: SCRecordingOutput, didFailWithError e: Error) { emit(["event": "error", "message": "\(e)"]) }
    func stream(_ s: SCStream, didStopWithError e: Error) { emit(["event": "error", "message": "\(e)"]) }
}
let delegate = Delegate(info)
let stream = SCStream(filter: filter, configuration: cfg, delegate: delegate)
let rc = SCRecordingOutputConfiguration()
rc.outputURL = out
rc.outputFileType = .mov
rc.videoCodecType = .h264
let rec = SCRecordingOutput(configuration: rc, delegate: delegate)
do {
    try stream.addRecordingOutput(rec)
    try await stream.startCapture()
} catch { fail("could not start capture: \(error)") }

let deadline = Date().addingTimeInterval(seconds)
while Date() < deadline && !FileManager.default.fileExists(atPath: stopFile) {
    try await Task.sleep(nanoseconds: 50_000_000)
}
try await stream.stopCapture()
try await Task.sleep(nanoseconds: 800_000_000)     // let the file finish writing
try? FileManager.default.removeItem(atPath: stopFile)
emit(["event": "saved", "path": out.path])
