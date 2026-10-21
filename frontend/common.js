// Общее: API, экранирование, markdown+KaTeX, тема, Monaco, вывод запусков, опрос заданий, графики.
/* global marked, DOMPurify, katex, require, monaco */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

async function api(path, opts = {}) {
  if (opts.json !== undefined) {
    opts.body = JSON.stringify(opts.json);
    opts.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, isErr = false) {
  const t = document.createElement("div");
  t.className = "toast" + (isErr ? " err" : "");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

const fmtMs = ms => {
  if (ms == null) return "—";
  const s = Math.floor(ms / 1000), h = Math.floor(s / 3600);
  const mm = String(Math.floor(s / 60) % 60).padStart(2, "0"), ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};
const fmtDate = s => (s ? s.replace("T", " ").slice(0, 16) : "—");
const fmtSize = b => b == null ? "" : b < 1024 ? `${b} Б` : b < 1048576 ? `${(b / 1024).toFixed(0)} КБ` : `${(b / 1048576).toFixed(1)} МБ`;
const KIND = { algo: "Алгоритм", ml: "ML" };
const GRADE_CLS = { "забыл": "err", "трудно": "warn", "нормально": "ok", "легко": "ok" };

// ---------------- тема ----------------
function theme() { return document.documentElement.dataset.theme || "dark"; }
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("theme", t); } catch { /* приватный режим */ }
  if (window.monaco) monaco.editor.setTheme(t === "light" ? "recall-light" : "recall-dark");
}

// ---------------- markdown + KaTeX ----------------
// Формулы вынимаем ДО markdown (иначе _ и * внутри $…$ станут курсивом); код не трогаем.
const MD_TOKENS = /(```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|(?<![\\$])\$(?!\s)[^$\n]+?(?<!\s)\$(?!\d))/g;
function md(text) {
  if (!text) return "";
  const math = [];
  const src = String(text).replace(MD_TOKENS, tok => {
    if (tok.startsWith("`")) return tok;
    const display = tok.startsWith("$$") || tok.startsWith("\\[");
    const body = display ? tok.slice(2, -2) : tok.slice(1, -1);
    try { math.push(katex.renderToString(body, { displayMode: display, throwOnError: false })); }
    catch { math.push(`<code>${esc(body)}</code>`); }
    return `@@MATH${math.length - 1}@@`;
  });
  return DOMPurify.sanitize(marked.parse(src, { gfm: true })).replace(/@@MATH(\d+)@@/g, (_, i) => math[+i]);
}

// ---------------- ANSI -> HTML ----------------
const ANSI = ["#555", "#EF4743", "#2CBB5D", "#FFC01E", "#5FA8FF", "#C38CFF", "#4FD1C5", "#CCC"];
function ansiHtml(text) {
  let out = "", fg = null, bold = false, open = false;
  const parts = String(text).split(/\x1b\[([0-9;]*)m/);
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) { out += esc(parts[i]); continue; }
    for (const c of (parts[i] || "0").split(";").map(Number)) {
      if (c === 0) { fg = null; bold = false; } else if (c === 1) bold = true;
      else if (c >= 30 && c <= 37) fg = ANSI[c - 30]; else if (c >= 90 && c <= 97) fg = ANSI[c - 90]; else if (c === 39) fg = null;
    }
    if (open) out += "</span>";
    open = !!(fg || bold);
    if (open) out += `<span style="${fg ? `color:${fg};` : ""}${bold ? "font-weight:600;" : ""}">`;
  }
  return out + (open ? "</span>" : "");
}
// \r внутри строки (прогресс-бары): остаётся напечатанное после последнего \r
const applyCR = t => String(t).split("\n").map(l => { const i = l.lastIndexOf("\r"); return i >= 0 ? l.slice(i + 1) : l; }).join("\n");

// ---------------- Monaco ----------------
let monacoReady = null;
const MONACO = "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.52.0/min";
function loadMonaco() {
  if (monacoReady) return monacoReady;
  // воркеры с CDN другого домена — через data:-прокси
  window.MonacoEnvironment = { getWorkerUrl: () => `data:text/javascript;charset=utf-8,${encodeURIComponent(
    `self.MonacoEnvironment={baseUrl:"${MONACO}/"};importScripts("${MONACO}/vs/base/worker/workerMain.js");`)}` };
  require.config({ paths: { vs: `${MONACO}/vs` } });
  monacoReady = new Promise(ok => require(["vs/editor/editor.main"], () => {
    const common = { "editorLineNumber.foreground": "#6E7681", "editorIndentGuide.background1": "#3A3A3A55" };
    monaco.editor.defineTheme("recall-dark", { base: "vs-dark", inherit: true, rules: [
      { token: "comment", foreground: "8B949E", fontStyle: "italic" }, { token: "keyword", foreground: "FF9D5C" },
      { token: "string", foreground: "A5D6A7" }, { token: "number", foreground: "79C0FF" }],
      colors: { ...common, "editor.background": "#1E1E1E", "editor.lineHighlightBackground": "#2A2A2A",
        "editorCursor.foreground": "#FFA116", "editor.selectionBackground": "#FFA11633" } });
    monaco.editor.defineTheme("recall-light", { base: "vs", inherit: true, rules: [
      { token: "comment", foreground: "6A737D", fontStyle: "italic" }, { token: "keyword", foreground: "C2410C" },
      { token: "string", foreground: "1A7F37" }, { token: "number", foreground: "0550AE" }],
      colors: { "editor.background": "#FFFFFF", "editor.lineHighlightBackground": "#F6F8FA",
        "editorCursor.foreground": "#E08800", "editor.selectionBackground": "#FFA11640", "editorLineNumber.foreground": "#9AA1AA" } });
    monaco.editor.setTheme(theme() === "light" ? "recall-light" : "recall-dark");
    registerPythonCompletion();
    ok(monaco);
  }));
  return monacoReady;
}

// Автодополнение: ключевые слова, встроенные функции и имена из всех файлов задачи
// (слова из открытых моделей Monaco подставляет сам — wordBasedSuggestions: "allDocuments").
const PY_WORDS = ("False None True and as assert async await break class continue def del elif else except finally for from global if import in "
  + "is lambda nonlocal not or pass raise return try while with yield print len range enumerate zip map filter sorted sum min max abs "
  + "isinstance list dict set tuple str int float bool open super self __init__ __name__ __main__").split(" ");
function registerPythonCompletion() {
  monaco.languages.registerCompletionItemProvider("python", {
    provideCompletionItems(model, pos) {
      const w = model.getWordUntilPosition(pos);
      const range = { startLineNumber: pos.lineNumber, endLineNumber: pos.lineNumber, startColumn: w.startColumn, endColumn: w.endColumn };
      const names = new Set(PY_WORDS);
      for (const m of monaco.editor.getModels()) {
        if (m.getLanguageId() !== "python") continue;
        for (const x of m.getValue().matchAll(/\b(?:def|class)\s+([A-Za-z_]\w*)|\b([A-Za-z_]\w{2,})\s*=/g)) names.add(x[1] || x[2]);
      }
      return { suggestions: [...names].map(n => ({ label: n, insertText: n, range,
        kind: PY_WORDS.includes(n) ? monaco.languages.CompletionItemKind.Keyword : monaco.languages.CompletionItemKind.Variable })) };
    },
  });
}

// ---------------- вывод запусков ----------------
let plotlyReady = null;
function loadPlotly() {
  if (window.Plotly) return Promise.resolve();
  plotlyReady ||= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js";
    const amd = window.define;  // иначе plotly зарегистрируется в загрузчике Monaco, а не в window
    window.define = undefined;
    s.onload = () => { window.define = amd; ok(); };
    s.onerror = () => { window.define = amd; fail(new Error("plotly не загрузился")); };
    document.head.appendChild(s);
  });
  return plotlyReady;
}

function tableHtml(t) {
  const head = t.columns.map((c, i) => `<th>${esc(c)}<span class="dt">${esc(t.dtypes?.[i] || "")}</span></th>`).join("");
  const body = t.rows.map(r => `<tr>${r.map(v => v == null ? '<td class="null">NaN</td>' : `<td>${esc(v)}</td>`).join("")}</tr>`).join("");
  const shown = t.rows.length < t.n_rows ? `, показаны первые ${t.rows.length}` : "";
  return `<div class="o-table">${t.title ? `<div class="cap"><b>${esc(t.title)}</b></div>` : ""}<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
    <div class="cap">${t.n_rows} строк × ${t.n_cols} колонок${shown}</div></div>`;
}

// outputs: [{type: stream, name, text} | {type: rich, type2...}]; rawUrl(path) — ссылка на файл картинки
function renderOutputs(el, outputs, rawUrl) {
  el.innerHTML = "";
  for (const o of outputs || []) {
    if (o.type === "stream") {
      const pre = document.createElement("pre");
      pre.className = "o-text" + (o.name === "stderr" ? " stderr" : "");
      pre.innerHTML = ansiHtml(applyCR(o.text));
      el.appendChild(pre);
    } else if (o.type === "table" || o.type === "rich" && o.columns) {
      el.insertAdjacentHTML("beforeend", tableHtml(o));
    } else if (o.path) {
      el.insertAdjacentHTML("beforeend", `${o.title ? `<div class="muted small">${esc(o.title)}</div>` : ""}<img class="o-img" alt="график" src="${rawUrl(o.path)}?t=${Date.now()}">`);
    } else if (o.figure) {
      const div = document.createElement("div");
      div.style.cssText = "width:100%;min-height:340px";
      el.appendChild(div);
      loadPlotly().then(() => window.Plotly.newPlot(div, o.figure.data || [], { ...(o.figure.layout || {}), autosize: true },
        { responsive: true, displaylogo: false })).catch(e => { div.textContent = e.message; });
    }
  }
}

// Опрос задания: onUpdate(outputs) по мере появления вывода; возвращает {result, outputs}
async function followJob(jobId, onUpdate, alive = () => true) {
  let outs = [], rev = 0;
  for (;;) {
    if (!alive()) return { result: null, outputs: outs };
    const r = await api(`/api/jobs/${jobId}?have=${outs.length}&rev=${rev}`);
    if (r.state === "lost") return { result: { status: "error" }, outputs: [...outs, { type: "stream", name: "stderr", text: "сервер потерял задание (перезапускался?)\n" }] };
    outs = r.reset ? r.outputs : outs.concat(r.outputs);
    rev = r.rev;
    onUpdate && onUpdate(outs);
    if (r.state === "done") return { result: r.result, outputs: outs };
    await new Promise(res => setTimeout(res, outs.length ? 250 : 400));
  }
}

// ---------------- результаты тестов ----------------
const TEST_ICON = { pass: ["ok", "✓"], fail: ["err", "✗"], error: ["err", "!"], broken: ["warn", "⚠"], skip: ["muted", "–"] };
function testsHtml(check) {
  if (!check) return '<div class="empty">Нажмите «Проверить», чтобы прогнать тесты.</div>';
  if (check.fatal && !check.tests?.length) return `<div class="err" style="padding:8px">${esc(check.fatal)}</div>`;
  const broken = check.broken ? ` · <span class="warn">${check.broken} сломан(о) на эталоне — не учитывается</span>` : "";
  const all = check.total && check.passed === check.total;
  return `<div class="summary-bar"><b class="${all ? "ok" : "err"}">${check.passed}/${check.total} тестов прошли</b>${broken}
      ${check.ms != null ? `<span class="muted small">${(check.ms / 1000).toFixed(1)} с</span>` : ""}</div>`
    + check.tests.map(t => {
      const [cls, ico] = TEST_ICON[t.status] || ["muted", "?"];
      return `<div class="test-row"><span class="${cls}">${ico}</span><span><b>${esc(t.name)}</b> <span class="muted small">${esc(t.file)}</span></span>
        <span class="muted small">${t.time ? t.time.toFixed(2) + " с" : ""}</span>
        ${t.message ? `<div class="msg">${esc(t.message.split("\n").slice(0, 4).join("\n"))}</div>` : ""}
        ${t.text ? `<details><summary class="muted small">traceback</summary><pre>${esc(t.text)}</pre></details>` : ""}</div>`;
    }).join("");
}

function diffHtml(text) {
  if (!text) return '<span class="muted">нет различий</span>';
  return text.split("\n").map(l => {
    const cls = l.startsWith("+++") || l.startsWith("---") ? "muted" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : "";
    return `<span class="${cls}">${esc(l)}</span>`;
  }).join("\n");
}

// ---------------- график (одна серия, без второй оси) ----------------
function lineChart(el, pts, o) {
  const H = 140, padL = 44, padR = 12, padT = 10, padB = 22;
  const draw = () => {
    const W = Math.max(240, el.clientWidth);
    const x = i => pts.length === 1 ? padL + (W - padL - padR) / 2 : padL + i * (W - padL - padR) / (pts.length - 1);
    const y = v => padT + (1 - v / o.max) * (H - padT - padB);
    const path = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(o.y(p)).toFixed(1)}`).join("");
    const every = Math.ceil(pts.length / 8);
    el.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="график">
      ${o.ticks.map(t => `<line x1="${padL}" x2="${W - padR}" y1="${y(t)}" y2="${y(t)}" class="grid"/><text x="${padL - 6}" y="${y(t) + 4}" text-anchor="end" class="axis">${o.fmt(t)}</text>`).join("")}
      ${pts.map((p, i) => i % every === 0 || i === pts.length - 1 ? `<text x="${x(i)}" y="${H - 5}" text-anchor="middle" class="axis">${i + 1}</text>` : "").join("")}
      <path d="${path}" class="series"/>${pts.map((p, i) => `<circle cx="${x(i)}" cy="${y(o.y(p))}" r="4" class="dot"/>`).join("")}
      <line class="cross" y1="${padT}" y2="${H - padB}" visibility="hidden"/><rect width="${W}" height="${H}" fill="transparent" class="hit"/></svg><div class="tip" hidden></div>`;
    const svg = $("svg", el), cross = $(".cross", el), tip = $(".tip", el), dots = $$(".dot", el);
    $(".hit", el).addEventListener("pointermove", e => {
      const mx = e.clientX - svg.getBoundingClientRect().left;
      let b = 0;
      pts.forEach((_, i) => { if (Math.abs(x(i) - mx) < Math.abs(x(b) - mx)) b = i; });
      cross.setAttribute("x1", x(b)); cross.setAttribute("x2", x(b)); cross.setAttribute("visibility", "visible");
      dots.forEach((d, i) => d.classList.toggle("hot", i === b));
      tip.hidden = false; tip.innerHTML = o.tip(pts[b], b);
      tip.style.left = Math.min(Math.max(0, x(b) - tip.offsetWidth / 2), W - tip.offsetWidth) + "px";
      tip.style.top = Math.max(0, y(o.y(pts[b])) - tip.offsetHeight - 10) + "px";
    });
    $(".hit", el).addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; dots.forEach(d => d.classList.remove("hot")); });
  };
  draw();
  new ResizeObserver(() => { if (Math.abs(el.clientWidth - (+$("svg", el)?.getAttribute("width") || 0)) > 4) draw(); }).observe(el);
}

// Оценка и время по попыткам — два графика, не одна ось на двоих
function historyCharts(box, items) {
  const pts = items.filter(p => p.total_ms != null);
  if (!pts.length) { box.innerHTML = '<div class="empty">сданных попыток нет</div>'; return; }
  box.innerHTML = '<div class="chart-title">оценка</div><div class="chart" data-c="s"></div><div class="chart-title">время</div><div class="chart" data-c="t"></div>';
  const tip = p => `${fmtDate(p.date)}<br>оценка <b>${p.score ?? "—"}</b> · время <b>${fmtMs(p.total_ms)}</b>`;
  lineChart($("[data-c=s]", box), pts, { y: p => p.score ?? 0, max: 100, ticks: [0, 50, 100], fmt: v => v, tip });
  const maxMs = Math.max(...pts.map(p => p.total_ms), 60000);
  const step = maxMs > 20 * 60000 ? 10 * 60000 : maxMs > 6 * 60000 ? 5 * 60000 : 60000;
  const top = Math.ceil(maxMs / step) * step;
  lineChart($("[data-c=t]", box), pts, { y: p => p.total_ms, max: top, ticks: [0, top / 2, top], fmt: fmtMs, tip });
}

// Перетаскивание папок: [{file, path}], path включает имя корневой папки
const SKIP = /(^|\/)(\.[^/]*|__pycache__|\.ipynb_checkpoints|venv|\.venv|node_modules)(\/|$)/;
async function collectDrop(dataTransfer) {
  const entries = [...dataTransfer.items].map(it => it.webkitGetAsEntry && it.webkitGetAsEntry()).filter(Boolean);
  const out = [];
  const fileOf = en => new Promise((ok, fail) => en.file(ok, fail));
  const readAll = async reader => { const all = []; for (;;) { const b = await new Promise((ok, fail) => reader.readEntries(ok, fail)); if (!b.length) return all; all.push(...b); } };
  async function walk(en) {
    const path = en.fullPath.replace(/^\//, "");
    if (SKIP.test(path)) return;
    if (en.isFile) out.push({ file: await fileOf(en), path });
    else if (en.isDirectory) for (const ch of await readAll(en.createReader())) await walk(ch);
  }
  for (const en of entries) await walk(en);
  if (!entries.length) [...dataTransfer.files].forEach(f => out.push({ file: f, path: f.name }));
  return out;
}

// ---------------- сравнение «по смыслу» ----------------
// Показываю исходный текст обеих версий, а подсвечиваю только строки, где отличается сам код
// (пробелы, пустые строки, комментарии, кавычки и docstring — не отличие).
const compareCode = (mine, ref) => api("/api/compare", { method: "POST", json: { mine, ref } });

async function semanticView(el, mine, ref, labels = ["эталон", "мой код"]) {
  await loadMonaco();
  const cmp = await compareCode(mine, ref);
  el.innerHTML = `<div class="sem-head"><span class="${cmp.equal ? "ok" : "warn"}">${cmp.equal ? "✓ по смыслу код совпадает с эталоном" : `совпадение по смыслу: ${cmp.similarity}%`}</span>
      <span class="muted small">подсвечены только строки, где отличается сам код; комментарии эталона — серые</span></div>
    <div class="sem-cols"><div><div class="sem-cap">${esc(labels[0])}</div><div class="sem-ed" data-s="ref"></div></div>
      <div><div class="sem-cap">${esc(labels[1])}</div><div class="sem-ed" data-s="mine"></div></div></div>`;
  const opts = { readOnly: true, automaticLayout: true, minimap: { enabled: false }, fontFamily: "JetBrains Mono, Menlo, monospace",
    fontSize: 13, fontLigatures: false, scrollBeyondLastLine: false, renderLineHighlight: "none" };
  const mk = (sel, text, marks, cls) => {
    const ed = monaco.editor.create($(`[data-s="${sel}"]`, el), { ...opts, value: text, language: "python" });
    ed.deltaDecorations([], [
      ...marks.changed.map(n => ({ range: new monaco.Range(n, 1, n, 1), options: { isWholeLine: true, className: cls, linesDecorationsClassName: cls + "-glyph" } })),
      ...marks.comments.map(n => ({ range: new monaco.Range(n, 1, n, 1), options: { isWholeLine: true, inlineClassName: "sem-comment" } })),
    ]);
    return ed;
  };
  const eds = [mk("ref", ref, cmp.ref, "sem-del"), mk("mine", mine, cmp.mine, "sem-add")];
  // общая прокрутка двух колонок
  eds[0].onDidScrollChange(e => { if (e.scrollTopChanged) eds[1].setScrollTop(e.scrollTop); });
  eds[1].onDidScrollChange(e => { if (e.scrollTopChanged) eds[0].setScrollTop(e.scrollTop); });
  return { cmp, dispose: () => eds.forEach(e => { const m = e.getModel(); e.dispose(); m && m.dispose(); }) };
}

// Переключатель «по смыслу / как написано» вокруг двух версий файла (по умолчанию — по смыслу)
async function diffSwitcher(el, mine, ref, labels) {
  let mode = "sem", view = null;
  el.innerHTML = `<div class="row" style="padding:6px 8px;border-bottom:1px solid var(--line)"><div class="seg" style="margin:0">
      <button data-d="sem">по смыслу</button><button data-d="raw">как написано</button></div></div><div class="diff-body" style="position:absolute;inset:40px 0 0 0"></div>`;
  if (getComputedStyle(el).position === "static") el.style.position = "relative";
  const body = $(".diff-body", el);
  const render = async () => {
    $$("[data-d]", el).forEach(b => b.classList.toggle("sel", b.dataset.d === mode));
    view && view.dispose();
    body.innerHTML = "";
    if (mode === "sem") { body.style.overflow = "auto"; view = await semanticView(body, mine, ref, labels); return; }
    await loadMonaco();
    const a = monaco.editor.createModel(ref, "python"), b = monaco.editor.createModel(mine, "python");
    const d = monaco.editor.createDiffEditor(body, { automaticLayout: true, readOnly: true, originalEditable: false, renderSideBySide: true,
      minimap: { enabled: false }, fontFamily: "JetBrains Mono, Menlo, monospace", fontSize: 13, fontLigatures: false });
    d.setModel({ original: a, modified: b });
    view = { dispose: () => { d.dispose(); a.dispose(); b.dispose(); } };
  };
  $$("[data-d]", el).forEach(b => b.onclick = () => { mode = b.dataset.d; render(); });
  await render();
  return { dispose: () => view && view.dispose() };
}
