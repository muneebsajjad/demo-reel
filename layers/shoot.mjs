// Screenshot many HTML layers in one browser session (a fresh Chrome per layer costs ~4 s each).
//   node layers/shoot.mjs jobs.json      jobs: [{ html, png, width, height }]
// Transparent background, device scale 1: the PNG is exactly width x height.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const jobs = JSON.parse(readFileSync(process.argv[2], "utf8"));
// the headless window must be at least as big as the largest layer, or Chrome leaves the rest unpainted
const maxW = Math.max(...jobs.map((j) => j.width)), maxH = Math.max(...jobs.map((j) => j.height));
const browser = await chromium.launch({ executablePath: process.env.CHROME, headless: true,
                                        args: [`--window-size=${maxW},${maxH + 200}`] });
const page = await browser.newPage({ deviceScaleFactor: 1, screen: { width: maxW, height: maxH + 200 },
                                     viewport: { width: maxW, height: maxH } });
for (const j of jobs) {
  await page.setViewportSize({ width: j.width, height: j.height });
  await page.goto(pathToFileURL(j.html).href, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: j.png, omitBackground: true });
  console.log("layer", j.name, "ok");
}
await browser.close();
