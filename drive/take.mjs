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
  page, ctx, sleep, now, out, get pointer() { return pointer; },
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
      : typeof target === "object" ? { ...target }            // literal CSS-px box (canvas drawings)
      : page.evaluate((sel) => document.querySelector(sel)?.getBoundingClientRect().toJSON(), target));
    if (r) r.dpr = await page.evaluate(() => devicePixelRatio);
    if (!r) throw new Error(`rect ${name}: nothing matched`);
    const k = r.dpr;
    log.rects[name] = { x: r.x * k, y: r.y * k, width: r.width * k, height: r.height * k, t: +now().toFixed(3) };
    return log.rects[name];
  },
};

// ---- a visible, human-paced pointer --------------------------------------------------------------
const POINTER = () => {
  if (window.__reelPointer) return;
  window.__reelPointer = true;
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `<style>
    .c { position: fixed; left: 0; top: 0; width: 26px; height: 26px; transform: translate(-100px,-100px);
         transition: opacity .2s; filter: drop-shadow(0 2px 3px rgba(0,0,0,.35)); }
    .r { position: fixed; left: 0; top: 0; width: 44px; height: 44px; margin: -22px 0 0 -22px; border-radius: 50%;
         background: rgba(80, 90, 255, .28); transform: scale(0); opacity: 0; }
    .r.on { animation: ripple .45s ease-out; }
    @keyframes ripple { from { transform: scale(.2); opacity: 1 } to { transform: scale(1.1); opacity: 0 } }
  </style><div class="r"></div><svg class="c" viewBox="0 0 26 26"><path d="M5 3 L5 21 L9.6 16.8 L12.8 23.4 L16 22 L12.9 15.6 L19 15.4 Z"
    fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
  const c = root.querySelector(".c"), r = root.querySelector(".r");
  const at = (e) => { c.style.transform = `translate(${e.clientX - 5}px, ${e.clientY - 3}px)`; };
  addEventListener("pointermove", at, true);
  addEventListener("pointerdown", (e) => { at(e); r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px";
    r.classList.remove("on"); void r.offsetWidth; r.classList.add("on"); }, true);
  const mount = () => (document.body || document.documentElement).appendChild(host);
  document.readyState === "loading" ? addEventListener("DOMContentLoaded", mount) : mount();
};
let pos = [cfg.width / 2, cfg.height / 3];
const easeIO = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
async function glide(to, ms) {
  const from = pos, n = Math.max(2, Math.round(ms / 16));
  const bow = [(to[1] - from[1]) * 0.08, (from[0] - to[0]) * 0.08];           // a slight natural curve
  for (let i = 1; i <= n; i++) {
    const u = easeIO(i / n), b = Math.sin(Math.PI * i / n);
    await page.mouse.move(from[0] + (to[0] - from[0]) * u + bow[0] * b, from[1] + (to[1] - from[1]) * u + bow[1] * b);
    await sleep(16);
  }
  pos = to;
}
async function pointAt(target) {
  if (Array.isArray(target)) return target;
  const box = await page.locator(target).first().boundingBox();
  if (!box) throw new Error(`pointer: nothing matched ${target}`);
  return [box.x + box.width / 2, box.y + box.height / 2];
}
const pointer = {
  async show() { await page.addInitScript(POINTER); await page.evaluate(POINTER); await page.mouse.move(...pos); },
  move: async (x, y, ms = 600) => glide([x, y], ms),
  async click(target, ms = 600) { await glide(await pointAt(target), ms); await sleep(90); await page.mouse.down();
    await sleep(70); await page.mouse.up(); await sleep(120); },
  async drag(from, to, ms = 900) { await glide(await pointAt(from), 450); await page.mouse.down(); await sleep(60);
    await glide(await pointAt(to), ms); await sleep(60); await page.mouse.up(); await sleep(120); },
  async type(text, cps = 14) { for (const ch of text) { await page.keyboard.type(ch); await sleep(1000 / cps * (0.7 + Math.random() * 0.6)); } },
  async key(k) { await page.keyboard.press(k); await sleep(120); },
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
