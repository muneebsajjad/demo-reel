// Launch Chrome for Testing in a throwaway profile, optionally with an unpacked extension.
// Branded Google Chrome no longer accepts --load-extension; Chrome for Testing does.
import { chromium } from "playwright-core";
import { existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// Chrome for Testing as installed by `npx playwright install chromium`, unless CHROME_PATH is set.
export function chromePath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const roots = [join(homedir(), "Library/Caches/ms-playwright"), join(homedir(), ".cache/ms-playwright")];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    for (const dir of readdirSync(root).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse()) {
      for (const sub of ["chrome-mac-arm64", "chrome-mac-x64", "chrome-mac"]) {
        const exe = join(root, dir, sub, "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing");
        if (existsSync(exe)) return exe;
      }
      const linux = join(root, dir, "chrome-linux/chrome");
      if (existsSync(linux)) return linux;
    }
  }
  throw new Error("Chrome for Testing not found: run `npx playwright install chromium` or set CHROME_PATH");
}

export const CFT_BUNDLE = "com.google.chrome.for.testing";

export async function launch({ width = 1600, height = 1000, x = 40, y = 30, extension, profile, scale } = {}) {
  profile ??= join(process.cwd(), ".demo-reel-profile");
  rmSync(profile, { recursive: true, force: true });
  mkdirSync(profile, { recursive: true });
  const args = [
    `--window-size=${width},${height}`, `--window-position=${x},${y}`,
    "--autoplay-policy=no-user-gesture-required", "--no-first-run", "--no-default-browser-check",
    "--disable-features=Translate,MediaRouter", "--force-color-profile=srgb",
  ];
  if (scale) args.push(`--force-device-scale-factor=${scale}`);
  if (extension) args.push(`--disable-extensions-except=${extension}`, `--load-extension=${extension}`);
  const ctx = await chromium.launchPersistentContext(profile, {
    headless: false, executablePath: chromePath(), viewport: null, args,
    // keep sound, no "controlled by automated software" bar, no --no-sandbox warning bar
    ignoreDefaultArgs: ["--mute-audio", "--enable-automation", "--disable-extensions", "--no-sandbox",
                        "--disable-component-extensions-with-background-pages", "--hide-scrollbars"],
  });
  const page = ctx.pages()[0] || (await ctx.newPage());
  return { ctx, page };
}

// The extension's service worker. Chrome may restart it at any time, so callers go through `inWorker`.
export async function worker(ctx) {
  const w = ctx.serviceWorkers().find((w) => w.url().startsWith("chrome-extension://"));
  return w || ctx.waitForEvent("serviceworker", { timeout: 15000 });
}

export async function inWorker(ctx, fn, arg) {
  for (let i = 0; i < 4; i++) {
    try { return await (await worker(ctx)).evaluate(fn, arg); }
    catch (e) { if (!/closed|destroyed/i.test(e.message)) throw e; await new Promise((r) => setTimeout(r, 300)); }
  }
  throw new Error("extension service worker unavailable");
}

export async function extensionId(ctx) {
  return new URL((await worker(ctx)).url()).host;
}
