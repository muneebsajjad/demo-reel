// Sawt 0.2: read an essay aloud, meanings on, word zoom switched on partway, popup stills after.
// Needs the Sawt engine running (sawt serve) and ./ext from prepare.sh.
import { writeFileSync } from "node:fs";

export const config = {
  url: "https://www.astralcodexten.com/p/heuristics-that-almost-always-work",
  width: 1700, height: 1090,
  extension: "./ext",
};

const ZOOM_AT = 5, STOP_AFTER = 12;   // sentence numbers
const command = (api, msg) => api.inWorker((m) => command(m), msg);   // the extension's own handler
const state = (api) => api.inWorker(() => getState());

export async function setup(api) {
  await api.inWorker((s) => chrome.storage.local.set(s),
    { meanings: "3.0", zoom: false, theme: "light", voice: "bm_fable", speed: 1.0 });
  await api.sleep(4000);                              // fonts and late layout
  await api.rect("title", "h1.post-title");
  await api.rect("body", ".body.markup");
  // Paragraphs by their opening words: sturdier than counting elements.
  const para = (start) => [...document.querySelectorAll(".body.markup p")]
    .find((p) => p.textContent.trim().startsWith(start)).getBoundingClientRect().toJSON();
  await api.rect("para1", para, "He works in a very boring building");
  await api.rect("para2", para, "It’s the wind");
  await api.rect("para3", para, "At some point");
  // Sawt draws its cards in a closed shadow root, beside the column: 24px right of it, level with
  // the sentence being read, 300px wide. Record where the two cards in this take will appear.
  const card = (start) => {
    const col = document.querySelector(".body.markup").getBoundingClientRect();
    const at = start ? [...document.querySelectorAll(".body.markup p")]
      .find((p) => p.textContent.trim().startsWith(start)) : document.querySelector("h1.post-title");
    return { x: col.right + 24, y: at.getBoundingClientRect().top, width: 300, height: 1 };
  };
  await api.rect("card1", card, null);
  await api.rect("card2", card, "At some point");
}

export async function run(api) {
  await api.sleep(1500);
  api.mark("read");
  await command(api, { cmd: "read" });
  let last = -1;
  while (true) {
    const s = await state(api);
    if (s.status === "error") throw new Error(s.error);
    const n = s.chunks?.[s.index]?.sentence ?? -1;
    if (n !== last) {
      last = n;
      api.mark("sentence", { n, text: s.sentences?.[n]?.slice(0, 70) });
      if (n === ZOOM_AT) { await command(api, { cmd: "zoom", value: true }); api.mark("zoom on"); }
      if (n > STOP_AFTER) break;
    }
    await api.sleep(50);
  }
  await api.sleep(400);
  api.chunks = (await state(api)).chunks;
}

// The popup at 3x, while still reading: once in light, then right after clicking its own
// "Dark" button, so both stills show the same moment.
export async function after(api) {
  await api.inWorker(() => chrome.storage.local.set({ theme: "light" }));
  const id = await api.extensionId();
  const pop = await api.ctx.newPage();
  const cdp = await api.ctx.newCDPSession(pop);
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: 352, height: 700, deviceScaleFactor: 3, mobile: false });
  await pop.goto(`chrome-extension://${id}/popup.html`);
  await api.sleep(1000);
  const h = await pop.evaluate(() => document.documentElement.scrollHeight);
  const shoot = async (theme) => {
    const { data } = await cdp.send("Page.captureScreenshot",
      { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width: 352, height: h, scale: 1 } });
    writeFileSync(`${api.out}-popup-${theme}.png`, Buffer.from(data, "base64"));
  };
  await shoot("light");
  await pop.click('input[name="theme"][value="dark"] + span');
  await api.sleep(250);
  await shoot("dark");
  await command(api, { cmd: "stop" });
}
