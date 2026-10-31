// Tidy: add a task, move cards across the board, finish one, switch to dark mode.
// The example to start from: a local page, no account, no sound (so the system picks music).
//   reel take scenario.mjs takes/take1
export const config = {
  url: new URL("./app/index.html", import.meta.url).href,
  width: 1500, height: 1000,
};

const card = (text) => `.card:has(.t:text-is("${text}"))`;

export async function setup(api) {
  await api.pointer.show();
  // camera targets, measured from the page
  await api.rect("header", "header");
  await api.rect("add", "#add");
  await api.rect("todo", '.col[data-col="todo"]');
  await api.rect("doing", '.col[data-col="doing"]');
  await api.rect("done", '.col[data-col="done"]');
  await api.rect("progress", ".progress");
  await api.rect("board", "main");
}

export async function run(api) {
  const p = api.pointer;
  await api.sleep(1200);

  api.mark("add");                                          // add a task
  await p.click("#new", 800);
  await p.type("Ship the demo video", 16);
  await api.sleep(250);
  await p.key("Enter");
  await api.sleep(1100);

  api.mark("move");                                         // To do -> Doing
  await p.drag(card("Record the demo"), '.col[data-col="doing"] .card:first-of-type', 1100);
  await api.sleep(900);

  api.mark("finish");                                       // Doing -> Done: the bar moves
  await p.drag(card("Fix the signup bug"), '.col[data-col="done"] h2', 1100);
  await api.sleep(1400);

  api.mark("dark");                                         // dark mode
  await p.click("#theme", 900);
  await api.sleep(1800);
  api.mark("end");
  await api.sleep(300);
}
