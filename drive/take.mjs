#!/usr/bin/env node
// Record one take of a scenario.
//
//   node drive/take.mjs <scenario.mjs> [--out takes/take1]
//
// A scenario is an ES module:
//   export const config = { url, width, height, extension, app }       // all optional but url
//   export async function setup(api) {}    // before recording: settings, login, warm-up
//   export async function run(api) {}      // while recording: the demo itself
//   export async function after(api) {}    // after recording stops: extra captures (stills)
//
// api = { page, ctx, sleep, mark(name, data?), rect(name, selector | fn), now(),
//         inWorker(fn, arg), extensionId(), out }
//
// Writes <out>.mov (picture and the app's own sound) and <out>.json:
//   { recording: {...from the recorder}, viewport: {x, y, width, height} in recording pixels,
//     events: [{t, name, ...}], rects: {name: {x, y, width, height, t}} in viewport pixels }
// Times are seconds from the first recorded frame; positions are pixels of the recording.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { CFT_BUNDLE, extensionId, inWorker, launch } from "./browser.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const argv = process.argv.slice(2);
const scenarioPath = resolve(argv.find((a) => !a.startsWith("--")) ?? "");
const out = resolve(argv.includes("--out") ? argv[argv.indexOf("--out") + 1] : "takes/take");
mkdirSync(dirname(out), { recursive: true });
const recorder = resolve(ROOT, "recorder/record");
if (!existsSync(recorder)) throw new Error("build the recorder first: recorder/build.sh");

const scenario = await import(pathToFileURL(scenarioPath));
const cfg = { width: 1600, height: 1000, ...scenario.config };
if (cfg.extension) cfg.extension = resolve(dirname(scenarioPath), cfg.extension);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { ctx, page } = await launch(cfg);
if (cfg.extension) await sleep(1200);             // let a fresh install open (and settle) its pages
for (const p of ctx.pages()) if (p !== page && p.url().startsWith("chrome-extension://")) await p.close();

let t0 = 0, recording = null;
const log = { events: [], rects: {} };
const now = () => (t0 ? (Date.now() - t0) / 1000 : 0);
const api = {
  page, ctx, sleep, now, out,
  inWorker: (fn, arg) => inWorker(ctx, fn, arg),
  extensionId: () => extensionId(ctx),
  mark(name, data = {}) {
    const e = { t: +now().toFixed(3), name, ...data };
    log.events.push(e);
    console.log(e.t.toFixed(2).padStart(7), name, Object.keys(data).length ? JSON.stringify(data) : "");
    return e;
  },
  // Where an element is, in pixels of the page viewport as recorded. `target` is a CSS selector,
  // or a function run in the page (with `arg`) that returns a DOMRect-like {x, y, width, height}
  // in CSS px. The function is serialised into the page, so it cannot use outer variables.
  async rect(name, target, arg) {
    const r = await (typeof target === "function"
      ? page.evaluate(target, arg)
      : page.evaluate((sel) => document.querySelector(sel)?.getBoundingClientRect().toJSON(), target));
    if (r) r.dpr = await page.evaluate(() => devicePixelRatio);
    if (!r) throw new Error(`rect ${name}: nothing matched`);
    const k = r.dpr;
    log.rects[name] = { x: r.x * k, y: r.y * k, width: r.width * k, height: r.height * k, t: +now().toFixed(3) };
    return log.rects[name];
  },
};

await page.goto(cfg.url, { waitUntil: "commit", timeout: 60000 });
await page.waitForLoadState("load", { timeout: 30000 }).catch(() => {});
await page.bringToFront();
// a page recorded before its stylesheets arrive is unusable: wait for every one of them
const styled = await page.waitForFunction(() =>
  document.readyState !== "loading" &&
  [...document.querySelectorAll('link[rel="stylesheet"]')].every((l) => l.sheet), null, { timeout: 45000 })
  .then(() => true, () => false);
if (!styled) throw new Error("stylesheets did not load: check the network and try again");
if (scenario.setup) await scenario.setup(api);

// where the page viewport sits inside the window, in CSS px: browser chrome is above it
const geo = await page.evaluate(() => ({ chrome: outerHeight - innerHeight, w: innerWidth, h: innerHeight, dpr: devicePixelRatio }));

const rec = spawn(recorder, ["--app", cfg.app ?? CFT_BUNDLE, "--out", out + ".mov", "--seconds", "600"],
                  { stdio: ["ignore", "pipe", "inherit"] });
const saved = new Promise((res) => {
  let buf = "";
  rec.stdout.on("data", (d) => {
    buf += d;
    for (let i; (i = buf.indexOf("\n")) >= 0; buf = buf.slice(i + 1)) {
      const line = JSON.parse(buf.slice(0, i));
      if (line.event === "started") { t0 = Date.now(); recording = line; }
      if (line.event === "error") { console.error("recorder:", line.message); process.exit(1); }
      if (line.event === "saved") res();
    }
  });
});
while (!t0) await sleep(20);

const s = recording.scale;
const win = recording.window;
log.recording = recording;
log.viewport = {
  x: Math.round(win.x * s), y: Math.round((win.y + win.height) * s - geo.h * geo.dpr),
  width: Math.round(geo.w * geo.dpr), height: Math.round(geo.h * geo.dpr),
};
api.mark("recording");
try {
  await scenario.run(api);
} finally {
  api.mark("stop");
  writeFileSync(out + ".mov.stop", "");
  await saved;
  if (scenario.after) await scenario.after(api);
  writeFileSync(out + ".json", JSON.stringify(log, null, 2));
  await ctx.close();
  console.log("wrote", out + ".mov", out + ".json");
}
