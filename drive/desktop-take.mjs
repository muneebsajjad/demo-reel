// A desktop take: native macOS apps instead of a browser page. take.mjs hands over to this when the
// scenario's config has `desktop`.
//
//   export const config = {
//     desktop: {
//       apps: ["io.github.you.app", "com.apple.TextEdit"],   // recorded together; the first picks the display
//       backdrop: ["#f4f3ff", "#dcdaf7"],                     // a clean surface behind the apps (optional)
//       cursor: true,                                         // record the real cursor (default true)
//     },
//   };
//
// api (on top of mark, sleep, now, out):
//   api.launch(app, {path, args, env})   start an app (path: run that binary, so `env` reaches it)
//   api.activate(app)                    bring it forward
//   api.window(app, {title, layer})      its window frame, global screen points {x, y, width, height}
//   api.place(app, {x, y, width, height}, {title, index})   move and size a window (Accessibility)
//   api.screen([x, y])                   the frame of the display holding that point (default: the
//                                        cursor's), global points
//   api.rect(name, target)               a camera target: {app, title?} for a window, or a literal
//                                        {x, y, width, height} in global points
//   api.pointer.move(x, y, ms) / .click([x, y] | {app, name} (a control's label) | {app, title?, at: [fx, fy]}, ms) / .type(text, cps) / .key(code, flags)
//   api.hold(key, ms) / api.modifier(key, down)   a push-to-talk key: "rightOption", "rightCommand", …
//   api.play(file)                       play a sound through the speakers (e.g. a voice line an app's
//                                        microphone should hear); resolves when it has finished
//   api.send(cmd)                        any drive/desktop command
// Rects and the viewport come out in pixels of the recording, as in a browser take, so the edit file
// works the same way.
import { spawn } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function desktopTake(scenario, scenarioPath, out) {
  const cfg = scenario.config.desktop;
  const helperPath = resolve(ROOT, "drive/desktop");
  if (!existsSync(helperPath)) throw new Error("build the desktop helper first: bin/reel setup");

  // ---- the helper: one JSON command per line --------------------------------------------------------
  const helper = spawn(helperPath, [], { stdio: ["pipe", "pipe", "inherit"] });
  const waiting = [];
  let buf = "";
  helper.stdout.on("data", (d) => {
    buf += d;
    for (let i; (i = buf.indexOf("\n")) >= 0; buf = buf.slice(i + 1)) waiting.shift()?.(JSON.parse(buf.slice(0, i)));
  });
  const send = (cmd) => new Promise((res, rej) => {
    waiting.push((r) => (r.error ? rej(new Error(`desktop ${cmd.op}: ${r.error}`)) : res(r)));
    helper.stdin.write(JSON.stringify(cmd) + "\n");
  });
  const check = spawn(helperPath, ["--check"]);
  if ((await new Promise((r) => check.on("exit", r))) !== 0)
    throw new Error("this terminal needs Accessibility permission to drive apps (System Settings → Privacy & Security → Accessibility)");

  // ---- geometry ---------------------------------------------------------------------------------------
  const frames = async (apps = cfg.apps) => (await send({ op: "frames", apps })).windows;
  async function window(app, { title, layer = 0 } = {}) {
    const ws = (await frames([app])).filter((w) => w.layer === layer && (title == null || w.title === title));
    if (!ws.length) throw new Error(`no window for ${app}${title ? ` titled "${title}"` : ""}`);
    return ws.sort((a, b) => b.width * b.height - a.width * a.height)[0];
  }
  // the display a point is on; by default the one under the cursor (where apps put their panels)
  async function screen(at) {
    const [x, y] = at ?? Object.values(await send({ op: "cursor" }));
    const { x: sx, y: sy, width, height } = await send({ op: "screen", x, y });
    return { x: sx, y: sy, width, height };
  }
  async function pointAt(target) {
    if (Array.isArray(target)) return target;
    const w = target.name ? await find(target.app, target.name)
            : target.app ? await window(target.app, target) : target;
    const [fx, fy] = target.at ?? [0.5, 0.5];
    return [w.x + w.width * fx, w.y + w.height * fy];
  }

  // a control by its label; web views build their accessibility tree a moment after being asked
  async function find(app, name) {
    for (let i = 0; ; i++) {
      try { return await send({ op: "find", app, name }); }
      catch (e) { if (i >= 12) throw e; await sleep(400); }
    }
  }

  let t0 = 0, recording = null;
  const log = { desktop: true, events: [], rects: {} };
  const raw = {};                                      // rects in global points, converted at the end
  const now = () => (t0 ? (Date.now() - t0) / 1000 : 0);
  const api = {
    out, sleep, now, send, frames, window, screen, find,
    mark(name, data = {}) {
      const e = { t: +now().toFixed(3), name, ...data };
      log.events.push(e);
      console.log(e.t.toFixed(2).padStart(7), name, Object.keys(data).length ? JSON.stringify(data) : "");
      return e;
    },
    async rect(name, target) {
      const r = target.app ? await window(target.app, target) : { ...target };
      raw[name] = { x: r.x, y: r.y, width: r.width, height: r.height, t: +now().toFixed(3) };
      return raw[name];
    },
    launch: (app, o = {}) => send({ op: "launch", app, ...o }),
    activate: (app) => send({ op: "activate", app }),
    place: (app, r, { title, index = 0 } = {}) => send({ op: "place", app, index, title, ...r }),
    modifier: (key, down) => send({ op: "modifier", key, down }),
    async hold(key, ms) { await api.modifier(key, true); await sleep(ms); await api.modifier(key, false); },
    play(file) {
      const p = spawn("/usr/bin/afplay", [resolve(dirname(scenarioPath), file)], { stdio: "ignore" });
      return new Promise((r) => p.on("exit", r));
    },
    pointer: {
      move: (x, y, ms = 600) => send({ op: "move", x, y, ms }),
      async click(target, ms = 600) { const [x, y] = await pointAt(target); await send({ op: "click", x, y, ms }); await sleep(120); },
      type: (text, cps = 14) => send({ op: "type", text, cps }),
      key: (code, flags = 0) => send({ op: "key", code, flags }),
    },
  };

  try {
    if (scenario.setup) await scenario.setup(api);

    // a clean surface behind the apps, on the display the first app is on
    const pids = [];
    if (cfg.backdrop) {
      const main = await window(cfg.apps[0]);
      const b = await send({ op: "backdrop", colors: cfg.backdrop, at: [main.x + 1, main.y + 1] });
      pids.push(b.pid);
      await sleep(300);
    }

    const recorder = resolve(ROOT, "recorder/record");
    const recArgs = ["--app", cfg.apps.join(","), "--out", out + ".mov", "--seconds", "600"];
    for (const p of pids) recArgs.push("--pid", String(p));
    if (cfg.cursor !== false) recArgs.push("--cursor");
    const rec = spawn(recorder, recArgs, { stdio: ["ignore", "pipe", "inherit"] });
    const saved = new Promise((res) => {
      let b = "";
      rec.stdout.on("data", (d) => {
        b += d;
        for (let i; (i = b.indexOf("\n")) >= 0; b = b.slice(i + 1)) {
          const line = JSON.parse(b.slice(0, i));
          if (line.event === "started") { t0 = Date.now(); recording = line; }
          if (line.event === "error") { console.error("recorder:", line.message); process.exit(1); }
          if (line.event === "saved") res();
        }
      });
    });
    while (!t0) await sleep(20);

    const s = recording.scale, o = recording.origin;
    log.recording = recording;
    log.viewport = { x: 0, y: 0, width: Math.round(recording.display.width * s), height: Math.round(recording.display.height * s) };
    api.mark("recording");
    try {
      await scenario.run(api);
    } finally {
      api.mark("stop");
      writeFileSync(out + ".mov.stop", "");
      await saved;
    }
    if (scenario.after) await scenario.after(api);
    for (const [name, r] of Object.entries(raw))
      log.rects[name] = { x: (r.x - o.x) * s, y: (r.y - o.y) * s, width: r.width * s, height: r.height * s, t: r.t };
    writeFileSync(out + ".json", JSON.stringify(log, null, 2));
    console.log("wrote", out + ".mov", out + ".json");
  } finally {
    await send({ op: "backdrop", show: false }).catch(() => {});
    if (scenario.teardown) await scenario.teardown(api).catch((e) => console.error("teardown:", e.message));
    helper.stdin.end();
  }
}
