// Общее для ноутбуков (эталон и попытка): markdown + формулы, выводы ядра, клиент ядра, панель.
/* global marked, DOMPurify, katex */

// ---------------- markdown + KaTeX ----------------
// Формулы вынимаем ДО markdown (иначе _ и * внутри $…$ станут курсивом), код не трогаем.
const MD_TOKENS = /(```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|(?<![\\$])\$(?!\s)[^$\n]+?(?<!\s)\$(?!\d))/g;

function md(text) {
  if (!text) return "";
  const math = [];
  const src = String(text).replace(MD_TOKENS, tok => {
    if (tok.startsWith("`")) return tok;
    const display = tok.startsWith("$$") || tok.startsWith("\\[");
    const body = display ? tok.slice(2, -2) : tok.slice(1, -1);
    math.push(renderTex(body, display));
    return `@@MATH${math.length - 1}@@`;
  });
  let html = DOMPurify.sanitize(marked.parse(src, { gfm: true, breaks: false }), { ADD_ATTR: ["target"] });
  html = html.replace(/@@MATH(\d+)@@/g, (_, i) => math[+i]);
  return html;
}

function renderTex(tex, display) {
  try { return katex.renderToString(tex, { displayMode: display, throwOnError: false, output: "html" }); }
  catch { return `<code>${esc(tex)}</code>`; }
}

function mdInto(el, text) {
  el.innerHTML = md(text);
  el.querySelectorAll("a[href^='http']").forEach(a => { a.target = "_blank"; a.rel = "noopener"; });
}

// ---------------- ANSI -> HTML (traceback, цветной вывод) ----------------
const ANSI_COLORS = ["#2b2b3a", "#FF4D6A", "#A6F04A", "#FFC93C", "#8FB8FF", "#C79BFF", "#7FE3E3", "#D9D6EA"];
const ANSI_BRIGHT = ["#77758F", "#FF7A90", "#C2F57E", "#FFD970", "#B3CEFF", "#DCC2FF", "#A8F0F0", "#FFFFFF"];

function ansi256(n) {
  if (n < 8) return ANSI_COLORS[n];
  if (n < 16) return ANSI_BRIGHT[n - 8];
  if (n >= 232) { const v = 8 + (n - 232) * 10; return `rgb(${v},${v},${v})`; }
  n -= 16;
  const c = [Math.floor(n / 36), Math.floor(n / 6) % 6, n % 6].map(x => (x ? 55 + x * 40 : 0));
  return `rgb(${c.join(",")})`;
}

function ansiHtml(text) {
  let out = "", fg = null, bold = false, open = false;
  const parts = String(text).split(/\x1b\[([0-9;]*)m/);
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) { out += esc(parts[i]); continue; }
    const codes = parts[i].split(";").filter(Boolean).map(Number);
    if (!codes.length) codes.push(0);
    for (let k = 0; k < codes.length; k++) {
      const c = codes[k];
      if (c === 0) { fg = null; bold = false; }
      else if (c === 1) bold = true;
      else if (c === 22) bold = false;
      else if (c >= 30 && c <= 37) fg = ANSI_COLORS[c - 30];
      else if (c >= 90 && c <= 97) fg = ANSI_BRIGHT[c - 90];
      else if (c === 39) fg = null;
      else if (c === 38 && codes[k + 1] === 5) { fg = ansi256(codes[k + 2]); k += 2; }
      else if (c === 38 && codes[k + 1] === 2) { fg = `rgb(${codes[k + 2]},${codes[k + 3]},${codes[k + 4]})`; k += 4; }
    }
    if (open) out += "</span>";
    open = !!(fg || bold);
    if (open) out += `<span style="${fg ? `color:${fg};` : ""}${bold ? "font-weight:600;" : ""}">`;
  }
  return out + (open ? "</span>" : "");
}

// \r внутри строки (tqdm, прогресс-бары): остаётся то, что напечатано после последнего \r
function applyCR(text) {
  return String(text).split("\n").map(line => {
    const i = line.lastIndexOf("\r");
    return i >= 0 ? line.slice(i + 1) : line;
  }).join("\n");
}

// ---------------- выводы ядра ----------------
let plotlyReady = null;
function loadPlotly() {
  if (window.Plotly) return Promise.resolve();
  plotlyReady ||= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js";
    s.onload = ok; s.onerror = () => fail(new Error("plotly не загрузился"));
    document.head.appendChild(s);
  });
  return plotlyReady;
}

// Относительные пути в HTML-выводе (Video("results/x.mp4"), <img src="data/…">) — к файлам папки эталона
function fixPaths(root, refId) {
  if (!refId) return;
  root.querySelectorAll("[src],[href]").forEach(el => {
    for (const attr of ["src", "href"]) {
      const v = el.getAttribute(attr);
      if (v && !/^(data:|blob:|https?:|\/|#|mailto:)/i.test(v)) el.setAttribute(attr, `/api/references/${refId}/raw/${v.replace(/^\.\//, "")}`);
    }
  });
}

function sanitizeHtml(html) {
  return DOMPurify.sanitize(html, {
    ADD_TAGS: ["audio", "video", "source", "track", "style"],
    ADD_ATTR: ["controls", "autoplay", "loop", "muted", "playsinline", "target", "colspan", "rowspan"],
    FORCE_BODY: true,
  });
}

function renderOutput(o, ctx = {}) {
  const box = document.createElement("div");
  box.className = "o";
  if (o.type === "stream") {
    box.className += " o-stream" + (o.name === "stderr" ? " o-stderr" : "");
    box.innerHTML = `<pre>${ansiHtml(applyCR(o.text))}</pre>`;
    return box;
  }
  if (o.type === "error") {
    box.className += " o-error";
    box.innerHTML = `<pre>${o.traceback ? ansiHtml(o.traceback) : esc(`${o.ename}: ${o.evalue}`)}</pre>`;
    return box;
  }
  // display_data / execute_result: самый богатый из понятных MIME-типов
  const d = o.data || {};
  if (o.count != null) box.dataset.out = `Out[${o.count}]`;
  if (d["application/vnd.plotly.v1+json"]) {
    const fig = d["application/vnd.plotly.v1+json"];
    const div = document.createElement("div");
    div.className = "o-plotly";
    box.appendChild(div);
    loadPlotly().then(() => window.Plotly.newPlot(div, fig.data || [], {
      ...(fig.layout || {}), autosize: true, paper_bgcolor: "#0E0E1A", plot_bgcolor: "#0E0E1A",
      font: { color: "#D9D6EA", family: "Inter, sans-serif" },
    }, { responsive: true, displaylogo: false })).catch(e => { div.textContent = e.message; });
  } else if (d["text/html"]) {
    box.className += " o-html";
    box.innerHTML = sanitizeHtml(Array.isArray(d["text/html"]) ? d["text/html"].join("") : d["text/html"]);
    fixPaths(box, ctx.refId);
  } else if (d["image/svg+xml"]) {
    const svg = Array.isArray(d["image/svg+xml"]) ? d["image/svg+xml"].join("") : d["image/svg+xml"];
    box.innerHTML = `<img class="o-img" alt="svg" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}">`;
  } else if (d["image/png"] || d["image/jpeg"] || d["image/gif"]) {
    const mime = d["image/png"] ? "image/png" : d["image/jpeg"] ? "image/jpeg" : "image/gif";
    box.innerHTML = `<img class="o-img" alt="изображение" src="data:${mime};base64,${String(d[mime]).replace(/\s/g, "")}">`;
  } else if (d["text/markdown"]) {
    box.className += " md";
    mdInto(box, d["text/markdown"]);
  } else if (d["text/latex"]) {
    const t = String(d["text/latex"]).trim().replace(/^\$\$?|\$\$?$/g, "");
    box.innerHTML = renderTex(t, true);
  } else if (d["application/json"]) {
    box.innerHTML = `<pre class="o-json">${esc(JSON.stringify(d["application/json"], null, 2))}</pre>`;
  } else if (d["text/plain"] != null) {
    box.innerHTML = `<pre>${ansiHtml(d["text/plain"])}</pre>`;
  }
  return box;
}

function renderOutputs(el, outputs, ctx = {}) {
  el.innerHTML = "";
  for (const o of outputs || []) el.appendChild(renderOutput(o, ctx));
}

// ---------------- клиент ядра ----------------
class KernelClient {
  constructor(key) { this.key = key; this.alive = true; }
  url(p) { return `/api/kernels/${this.key}/${p}`; }
  async state() { return (await api(this.url("state"))).kernel; }
  async start() { return (await api(this.url("start"), { method: "POST" })).kernel; }
  interrupt() { return api(this.url("interrupt"), { method: "POST" }); }
  restart() { return api(this.url("restart"), { method: "POST" }); }
  stop(keepalive = false) { return fetch(this.url("stop"), { method: "POST", keepalive }).catch(() => {}); }

  // Выполнить код; onUpdate(outputs, state) вызывается по мере появления вывода.
  async run(code, onUpdate, extra = {}) {
    const { job } = await api(this.url("execute"), { method: "POST", json: { code, ...extra } });
    let outs = [], rev = 0;
    for (;;) {
      if (!this.alive) return { status: "cancelled", outputs: outs };
      const r = await api(`${this.url("jobs/" + job)}?have=${outs.length}&rev=${rev}`);
      if (r.state === "lost") return { status: "error", outputs: [{ type: "error", ename: "Ошибка", evalue: "сервер потерял задание (перезапускался?)" }] };
      outs = r.reset ? r.outputs : outs.concat(r.outputs);
      rev = r.rev;
      onUpdate && onUpdate(outs, r.state);
      if (r.state === "done") return { ...r.result, outputs: outs };
      await new Promise(res => setTimeout(res, outs.length ? 250 : 400));
    }
  }
}

// ---------------- панель инструментов ----------------
// items: [{id, icon, label, title, cls}] — рисует ряд кнопок; клик -> handlers[id]()
function toolbar(el, items, handlers) {
  el.className = "nbbar-tools";
  el.innerHTML = items.map(it => it === "|" ? '<span class="sep"></span>'
    : `<button class="tb ${it.cls || ""}" data-tb="${it.id}" title="${esc(it.title || it.label)}"><span class="ico">${it.icon}</span><span class="lbl">${esc(it.label)}</span></button>`).join("")
    + '<span class="grow"></span><span class="kstate" data-kstate>ядро: —</span>';
  el.querySelectorAll("[data-tb]").forEach(b => b.onclick = () => handlers[b.dataset.tb] && handlers[b.dataset.tb]());
  return {
    setKernel(s) {
      const k = el.querySelector("[data-kstate]");
      const names = { idle: "готово", busy: "выполняется", starting: "запускается", off: "выключено", restarting: "перезапуск" };
      k.textContent = "ядро: " + (names[s] || s);
      k.className = "kstate " + (s === "busy" || s === "starting" || s === "restarting" ? "warn" : s === "idle" ? "ok" : "muted");
    },
  };
}

const TB = {
  add: { id: "add", icon: "+", label: "ячейка", title: "добавить ячейку ниже выбранной" },
  up: { id: "up", icon: "↑", label: "", title: "переместить вверх" },
  down: { id: "down", icon: "↓", label: "", title: "переместить вниз" },
  run: { id: "run", icon: "▶", label: "запустить", title: "запустить выбранную (Shift+Enter)" },
  runAll: { id: "runAll", icon: "▶▶", label: "все", title: "запустить все ячейки по порядку" },
  clear: { id: "clear", icon: "⌫", label: "очистить", title: "очистить выводы всех ячеек" },
  stop: { id: "stop", icon: "■", label: "прервать", title: "прервать выполнение (KeyboardInterrupt)" },
  restart: { id: "restart", icon: "↻", label: "перезапуск", title: "перезапустить ядро (переменные пропадут)" },
  off: { id: "off", icon: "⏻", label: "выключить", title: "выключить ядро (освободить память)" },
};
