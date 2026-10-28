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

// ---------------- тема: тёмная / светлая / как в системе ----------------
const darkMQ = window.matchMedia("(prefers-color-scheme: dark)");
function themePref() { try { return localStorage.getItem("theme") || "dark"; } catch { return "dark"; } }
function theme() { return document.documentElement.dataset.theme || "dark"; }
function applyTheme() {
  const pref = themePref();
  document.documentElement.dataset.theme = pref === "system" ? (darkMQ.matches ? "dark" : "light") : pref;
  if (window.monaco) defineMonacoThemes();
}
function setTheme(t) {
  try { localStorage.setItem("theme", t); } catch { /* приватный режим */ }
  applyTheme();
}
darkMQ.addEventListener?.("change", () => { if (themePref() === "system") applyTheme(); });
// цвет из токенов текущей темы (для Monaco, canvas и SVG)
const tok = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
// категория кирпичика -> класс .c-*, он задаёт --c
const CAT_CLASS = { preprocessing: "c-pre", layers: "c-lay", activations: "c-act", losses: "c-los", optimizers: "c-opt", metrics: "c-met",
                    comparison: "c-cmp", models: "c-mod" };
const CAT_TITLE = { preprocessing: "Preprocessing", layers: "Layers", activations: "Activations", losses: "Losses", optimizers: "Optimizers",
                    metrics: "Metrics", comparison: "Comparison", models: "Models" };
const catClass = c => CAT_CLASS[String(c || "").toLowerCase()] || "";

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
const ANSI = ["var(--text-3)", "var(--fail-text)", "var(--ok-text)", "var(--due-text)", "var(--new-text)", "var(--py-keyword)", "var(--py-builtin)", "var(--text)"];
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
    // встроенный токенизатор Python грузится лениво и перекрыл бы наш — ставим свой после него
    monaco.languages.onLanguage("python", () => require(["vs/basic-languages/python/python"], () => setTimeout(registerPythonTokens, 30)));
    defineMonacoThemes();
    registerPythonCompletion();
    ok(monaco);
  }));
  return monacoReady;
}

// Темы Monaco — из CSS-токенов текущей темы (стр. 27): поверхности, текст, акцент, подсветка Python
function defineMonacoThemes() {
  const h = n => tok(n).replace("#", "").slice(0, 6);
  const name = theme() === "light" ? "recall-light" : "recall-dark";
  monaco.editor.defineTheme(name, { base: theme() === "light" ? "vs" : "vs-dark", inherit: true, rules: [
    { token: "", foreground: h("--text") },
    { token: "keyword", foreground: h("--py-keyword") }, { token: "function", foreground: h("--py-function") },
    { token: "string", foreground: h("--py-string") }, { token: "number", foreground: h("--py-number") },
    { token: "comment", foreground: h("--py-comment"), fontStyle: "italic" },
    { token: "self", foreground: h("--py-self") }, { token: "builtin", foreground: h("--py-builtin") },
    { token: "operator", foreground: h("--py-operator") }, { token: "delimiter", foreground: h("--py-operator") },
    { token: "decorator", foreground: h("--py-function") }],
    colors: { "editor.background": tok("--editor"), "editor.foreground": tok("--text"), "editorLineNumber.foreground": tok("--text-3"),
      "editorLineNumber.activeForeground": tok("--text"), "editor.lineHighlightBackground": tok("--panel-2"), "editor.lineHighlightBorder": tok("--panel-2"),
      "editorCursor.foreground": tok("--accent-text"), "editor.selectionBackground": tok("--accent") + "44", "editorIndentGuide.background1": tok("--line"),
      "editorWidget.background": tok("--panel-2"), "editorWidget.border": tok("--line-2"), "editorSuggestWidget.background": tok("--panel-2"),
      "editorSuggestWidget.selectedBackground": tok("--panel-3"), "scrollbarSlider.background": tok("--line-2") + "88",
      "editorGutter.background": tok("--editor"), "minimap.background": tok("--editor") } });
  monaco.editor.setTheme(name);
}

// Python: свой токенизатор — функции, self, встроенные имена и операторы отдельными цветами
function registerPythonTokens() {
  const keywords = "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case".split(" ");
  const builtins = "abs all any bool dict enumerate filter float int isinstance len list map max min object open print range repr reversed round set sorted str sum super tuple type zip Exception ValueError TypeError KeyError IndexError RuntimeError NotImplementedError".split(" ");
  monaco.languages.setMonarchTokensProvider("python", {
    keywords, builtins,
    tokenizer: {
      root: [
        [/#.*$/, "comment"],
        [/@[a-zA-Z_][\w.]*/, "decorator"],
        [/[rRbBuUfF]{0,2}"""/, "string", "@tdq"], [/[rRbBuUfF]{0,2}'''/, "string", "@tsq"],
        [/[rRbBuUfF]{0,2}"([^"\\]|\\.)*"/, "string"], [/[rRbBuUfF]{0,2}'([^'\\]|\\.)*'/, "string"],
        [/\b(self|cls)\b/, "self"],
        [/[a-zA-Z_]\w*(?=\s*\()/, { cases: { "@keywords": "keyword", "@builtins": "builtin", "@default": "function" } }],
        [/[a-zA-Z_]\w*/, { cases: { "@keywords": "keyword", "@builtins": "builtin", "@default": "identifier" } }],
        [/0[xX][0-9a-fA-F]+|\d+(\.\d+)?([eE][-+]?\d+)?j?/, "number"],
        [/[+\-*/%=<>!&|^~:]+/, "operator"],
        [/[()[\]{},.;]/, "delimiter"],
      ],
      tdq: [[/"""/, "string", "@pop"], [/[^"]+|"/, "string"]],
      tsq: [[/'''/, "string", "@pop"], [/[^']+|'/, "string"]],
    },
  });
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
// Строка ошибки в моём коде: последний кадр traceback-а pytest в одном из моих файлов («solution.py:23: in loss»).
// Если assert упал в самом тесте и моих кадров нет — ищем def функции, которую тест вызвал (model.loss(…), «where loss = …»).
function errorLine(text, files, code = {}) {
  let found = null;
  for (const m of (text || "").matchAll(/(?:^|[\s"'\/])([\w.\-]+\.py)"?(?::|, line )(\d+)/gm)) {
    if (files.includes(m[1])) found = { file: m[1], line: +m[2] };
  }
  if (found) return found;
  const names = [];
  for (const m of (text || "").matchAll(/where (\w+) = <[\w.]+ object at|\.(\w+)\(|= (\w+)\(/g)) {
    const n = m[1] || m[2] || m[3];
    if (n && !names.includes(n)) names.push(n);
  }
  for (const n of names) for (const f of files) {
    const i = (code[f] || "").split("\n").findIndex(l => new RegExp(`^\\s*(async\\s+)?def\\s+${n}\\b`).test(l));
    if (i >= 0) return { file: f, line: i + 1, fn: n };
  }
  return null;
}

// «assert 0.91 >= 0.95» -> получено 0.91, ожидалось >= 0.95; «isclose(tensor(6.33), tensor(4.33))» -> ≈
function expectedGot(message, text = "") {
  const all = (message || "") + "\n" + (text || "");
  const isName = v => /^[A-Za-z_]\w*$/.test(String(v).trim()) && !/^(True|False|None|nan|inf)$/.test(String(v).trim());
  const ok = r => r && !isName(r.got) && !isName(r.expected) ? r : null;
  // pytest: «where False = <function allclose …>(1.0, 0.6667, equal_nan=True)» — значения, а не имена
  const arg = "([^,()\\[\\]]+(?:\\([^()\\[\\]]*\\))?|\\[[^\\]]*\\])";
  let c = all.match(new RegExp(`(?:isclose|allclose|array_equal)[^(\\n]*\\(${arg},\\s*${arg}(?:,[^)\\n]*)?\\)`, "m"));
  let r = c && ok({ got: c[1].trim(), op: "≈", expected: c[2].trim() });
  if (r) return r;
  // сообщение теста: «полнота 1.0 ≠ sklearn 0.6667»
  const val = "(-?[\\d.]+(?:e[-+]?\\d+)?|nan|inf|True|False|None|\\[[^\\]]*\\])";
  c = (message || "").match(new RegExp(`${val}\\s*(?:≠|!=)\\s*(?:[A-Za-zА-Яа-я_]+\\s+)?${val}`));
  r = c && ok({ got: c[1], op: "=", expected: c[2] });
  if (r) return r;
  const first = (message || "").split("\n").find(l => /\bassert\b/.test(l));
  const m = first && first.match(/\bassert\s+(.+?)\s+(==|!=|>=|<=|<|>|is not|is|not in|in)\s+(.+)$/);
  return m ? ok({ got: m[1], op: m[2], expected: m[3] }) : null;
}

// проверка режима (не тест поведения): файлы tests/library|scratch раскладываются как test_<режим>__<имя>
const modeCheckOf = t => (/^tests\/test_(library|scratch)__/.exec(t.file || "") || /^test_(library|scratch)__/.exec(t.file || "") || [])[1] || null;
function testsCount(check) {
  const all = arr(check.tests), mc = all.filter(modeCheckOf), rest = all.filter(t => !modeCheckOf(t));
  const ok = l => l.filter(t => t.status === "pass").length;
  return `${ok(rest)}/${rest.length}${mc.length ? ` · режим ${ok(mc)}/${mc.length}` : ""}`;
}
function testsHtml(check, opts = {}) {
  if (!check) return emptyState({ icon: "flask", title: "Тесты ещё не запускали", text: "«Проверить» прогонит тесты, попытка не засчитывается." });
  if (check.fatal && !check.tests?.length) return `<div class="err" style="padding:8px">${esc(check.fatal)}</div>`;
  if (!arr(check.tests).length) return emptyState({ icon: "flask", tone: "due", title: "У задачи нет тестов", text: "Добавьте <span class=\"mono\">test_*.py</span> в tests/, и задача станет полноценной." });
  const failed = t => ["fail", "error"].includes(t.status);
  const groups = [];
  const groupOf = (key, make) => groups.find(g => g.key === key) || (groups.push({ key, tests: [], ...make() }), groups[groups.length - 1]);
  for (const t of check.tests) {
    const mc = modeCheckOf(t);
    const g = mc ? groupOf("mode", () => ({ title: "Проверки режима", note: "не тесты: как именно написан код", mode: true }))
      : t.brick ? groupOf(`b:${t.brick}`, () => ({ title: t.brick, note: `bricks/${t.brick}.py${t.mode ? ` · ${MODE_NAME[t.mode] || t.mode}` : ""}`, mono: true }))
      : groupOf("task", () => ({ title: opts.taskTitle || "тесты задачи", note: "", mono: false }));
    g.tests.push(t);
  }
  // кирпичики первыми, потом задача, проверки режима — в конце
  groups.sort((a, b) => (a.key === "mode") - (b.key === "mode") || (a.key === "task") - (b.key === "task"));
  const broken = check.broken ? `<span class="warn small">${check.broken} сломано на эталоне — не учитывается</span>` : "";
  const one = t => {
    const eg = expectedGot(t.message, t.text), loc = opts.files && errorLine(t.text, opts.files, opts.code);
    const mc = modeCheckOf(t), first = (t.message || "").split("\n")[0];
    const exc = /^(\w+(Error|Exception))\b/.exec(first)?.[1];
    const what = mc ? `${modeBadge(mc, { short: true })} ${esc(first.replace(/^AssertionError:\s*/, ""))}`
      : eg ? `<b class="mono">${esc(t.name)}</b> <span class="faint">— ожидалось</span> <span class="ok mono">${esc(eg.expected)}</span><span class="faint">, получено</span> <span class="err mono">${esc(eg.got)}</span>`
      : `<b class="mono">${esc(t.name)}</b> <span class="faint">— ${esc(exc || first.slice(0, 120))}</span>`;
    const detail = !mc && !eg && t.message && t.message.split("\n").length > 1 ? `<div class="t-box"><pre>${esc(t.message.split("\n").slice(0, 8).join("\n"))}</pre></div>` : "";
    return `<div class="t-row fail"><i class="t-dot fail"></i><div class="t-main">${what}${detail}
        ${t.text ? `<details><summary class="faint small">traceback</summary><pre class="t-tb">${esc(t.text)}</pre></details>` : ""}</div>
      ${loc ? `<button class="link small" data-loc="${esc(loc.file)}:${loc.line}" title="${esc(loc.file)}">строка ${loc.line}</button>` : ""}</div>`;
  };
  const head = `<div class="t-head"><span class="${check.passed === check.total ? "ok" : "err"}"><b>${check.passed}/${check.total}</b> прошли</span>${broken}<span class="grow"></span>
    <span class="faint small">${check.ms != null ? `проверка ${(check.ms / 1000).toFixed(1)} с` : ""}${opts.checkNo ? ` · ${opts.checkNo}-я в этой попытке` : ""}</span>
    <div class="seg" style="margin:0"><button data-tf="all" class="sel">Все</button><button data-tf="failed">Упавшие</button></div></div>`;
  return head + groups.map(g => {
    const bad = g.tests.filter(failed), good = g.tests.filter(t => t.status === "pass"), other = g.tests.filter(t => !failed(t) && t.status !== "pass");
    const n = `<span class="t-count ${bad.length ? "fail" : "ok"}">${good.length}/${g.tests.length}</span>`;
    return `<details class="t-group ${bad.length ? "has-fail" : "all-ok"} ${g.mode ? "t-modes" : ""}" ${bad.length ? "open" : ""}>
      <summary>${g.mode ? "" : '<i class="t-sq"></i>'}<b class="${g.mono ? "mono" : ""}">${esc(g.title)}</b>${n}<span class="faint small">${esc(g.note)}</span></summary>
      ${bad.map(one).join("")}
      ${other.map(t => `<div class="t-row"><i class="t-dot skip"></i><div class="t-main"><b class="mono">${esc(t.name)}</b> <span class="faint">— ${esc(t.status)}</span></div></div>`).join("")}
      ${good.length ? `<div class="t-row ok"><i class="t-dot ok"></i><div class="t-main faint">${bad.length ? "ещё " : "все "}${good.length} ${plural(good.length, "прошёл", "прошли", "прошли")}: <span class="mono">${good.map(t => esc(t.name)).join(", ")}</span></div></div>` : ""}
    </details>`;
  }).join("");
}

// версия Python и пакеты окружения (кэш на сессию)
const pyInfoCache = {};
function pythonInfo(path) {
  return pyInfoCache[path] ||= api("/api/python/check", { method: "POST", json: { path } }).catch(() => null);
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

// ---------------- режимы: «Библиотека» (через готовую функцию) и «С нуля» (своими руками) ----------------
const MODES = ["library", "scratch"];
const MODE_NAME = { library: "библиотека", scratch: "с нуля" };
const MODE_TITLE = { library: "Библиотека", scratch: "С нуля" };
const HALF = { new: ["muted", "○", "новая"], due: ["warn", "⟳", "пора повторить"], solved: ["ok", "✓", "решено"], learned: ["ok", "✓", "выучено"],
               weak: ["err", "!", "слабо"], none: ["none", "–", "нет режима"], planned: ["none", "◌", "запланировано"], concept: ["none", "◌", "концепт"] };
// статус двух режимов (.ms): две маленькие иконки — книга (библиотека) и шестерёнка (с нуля), цвет — статус
const MS_CLS = { new: "new", due: "due", solved: "ok", learned: "ok", weak: "fail", none: "none", planned: "none", concept: "none" };
function modeHalves(statuses) {
  return `<span class="ms">${MODES.map(m => {
    const st = (statuses || {})[m] || "none", [, , t] = HALF[st] || HALF.none;
    return `<span class="ms-i ${MS_CLS[st] || "none"}" title="${MODE_TITLE[m]}: ${t}">${ICON[MODE_ICON[m]]}</span>`;
  }).join("")}</span>`;
}
// крупный вариант для таблиц: «книга выучено | шестерёнка слабо»
const PAIR_TEXT = { new: "новая", due: "пора", solved: "решено", learned: "выучено", weak: "слабо", none: "нет режима", planned: "план", concept: "концепт" };
function modePair(statuses) {
  return `<span class="mpair">${MODES.map(m => {
    const st = (statuses || {})[m] || "none";
    return `<span class="mp ${MS_CLS[st] || "none"}" title="${MODE_TITLE[m]}">${ICON[MODE_ICON[m]]}${PAIR_TEXT[st] || st}</span>`;
  }).join("")}</span>`;
}
// ---------------- иконки (16 px, цвет — currentColor) ----------------
const svg = (body, vb = "0 0 16 16") => `<svg viewBox="${vb}" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
const ICON = {
  logo: svg('<path d="M5.5 4 2 8l3.5 4M10.5 4 14 8l-3.5 4"/><circle cx="8" cy="8" r="1.4" fill="currentColor" stroke="none"/>'),
  book: svg('<rect x="3.5" y="2.5" width="9" height="11" rx="1.5"/><path d="M6 2.5v11"/>'),
  gear: svg('<circle cx="8" cy="8" r="2.2" fill="currentColor" stroke="none"/><path d="M8 1.8v2M8 12.2v2M1.8 8h2M12.2 8h2M3.6 3.6l1.4 1.4M11 11l1.4 1.4M3.6 12.4 5 11M11 5l1.4-1.4"/>'),
  flame: svg('<path d="M8 14c2.5 0 4-1.6 4-3.8C12 7 9 6 9 2.5 6.5 4 5.5 6 6 8 5 7.6 4.5 6.8 4.4 6 3.6 7 4 8.4 4 10.2 4 12.4 5.5 14 8 14Z"/>'),
  moon: svg('<path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5Z"/>'),
  sun: svg('<circle cx="8" cy="8" r="3"/><path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1"/>'),
  system: svg('<rect x="2" y="3" width="12" height="8.5" rx="1.5"/><path d="M6 14h4M8 11.5V14"/>'),
  chevron: svg('<path d="m6 4 4 4-4 4"/>'),
  check: svg('<path d="m3.5 8.5 3 3 6-7"/>'),
  x: svg('<path d="m4 4 8 8M12 4l-8 8"/>'),
  play: svg('<path d="M5 3.5v9l7-4.5-7-4.5Z" fill="currentColor"/>'),
  stop: svg('<rect x="4" y="4" width="8" height="8" rx="1.2" fill="currentColor"/>'),
  plus: svg('<path d="M8 3v10M3 8h10"/>'),
  search: svg('<circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/>'),
  lock: svg('<rect x="3.5" y="7" width="9" height="6.5" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>'),
  upload: svg('<path d="M8 11V3M4.5 6.5 8 3l3.5 3.5M3 13h10"/>'),
  flask: svg('<path d="M6 2h4M6.5 2v4L3 13h10L9.5 6V2"/>'),
  files: svg('<path d="M4 2.5h5l3 3v8H4z"/><path d="M9 2.5v3h3"/>'),
  table: svg('<rect x="2.5" y="3" width="11" height="10" rx="1.2"/><path d="M2.5 6.5h11M2.5 9.8h11M6.5 6.5V13"/>'),
  image: svg('<rect x="2.5" y="3" width="11" height="10" rx="1.2"/><circle cx="6" cy="6.5" r="1.2"/><path d="m3 12 3.5-3.5 2.5 2.5 1.5-1.5 2.5 2.5"/>'),
  panel: svg('<rect x="2.5" y="3" width="11" height="10" rx="1.2"/><path d="M6.5 3v10"/>'),
  clock: svg('<circle cx="8" cy="8.5" r="5"/><path d="M8 6v2.7l1.8 1.1M6.5 2h3"/>'),
  arrowUp: svg('<path d="M8 13V3.5M4 7.5l4-4 4 4"/>'),
  blocks: svg('<rect x="5.5" y="2.5" width="5" height="4" rx="1"/><rect x="2.5" y="9.5" width="5" height="4" rx="1"/><rect x="8.5" y="9.5" width="5" height="4" rx="1"/>'),
  // уровни: кирпичик — столбик, блок — 2×2, стена — 3×2
  brick: svg('<rect x="6.5" y="3" width="3" height="4" rx=".6" fill="currentColor" stroke="none"/><rect x="6.5" y="9" width="3" height="4" rx=".6" fill="currentColor" stroke="none"/>'),
  block: svg('<rect x="3" y="3.5" width="4" height="4" rx=".8" fill="currentColor" stroke="none"/><rect x="9" y="3.5" width="4" height="4" rx=".8" fill="currentColor" stroke="none"/><rect x="3" y="9" width="4" height="4" rx=".8" fill="currentColor" stroke="none"/><rect x="9" y="9" width="4" height="4" rx=".8" fill="currentColor" stroke="none"/>'),
  wall: svg('<rect x="1.5" y="4" width="3.6" height="3.4" rx=".6" fill="currentColor" stroke="none"/><rect x="6.2" y="4" width="3.6" height="3.4" rx=".6" fill="currentColor" stroke="none"/><rect x="10.9" y="4" width="3.6" height="3.4" rx=".6" fill="currentColor" stroke="none"/><rect x="1.5" y="8.6" width="3.6" height="3.4" rx=".6" fill="currentColor" stroke="none"/><rect x="6.2" y="8.6" width="3.6" height="3.4" rx=".6" fill="currentColor" stroke="none"/><rect x="10.9" y="8.6" width="3.6" height="3.4" rx=".6" fill="currentColor" stroke="none"/>'),
};
const MODE_ICON = { library: "book", scratch: "gear" };

// бейдж режима: «Библиотека» — книга, контур; «С нуля» — шестерёнка, заливка
function modeBadge(mode, { short = false } = {}) {
  return `<span class="mb mb-${mode === "library" ? "lib" : "scr"}">${ICON[MODE_ICON[mode]] || ""}${short ? MODE_NAME[mode] : MODE_TITLE[mode]}</span>`;
}
// метка уровня: кирпичик / блок / стена
const LEVEL_TITLE = { brick: "кирпичик", block: "блок", wall: "стена" };
function levelTag(level) {
  level = LEVEL_TITLE[level] ? level : "brick";
  return `<span class="lvl">${ICON[level]}${LEVEL_TITLE[level]}</span>`;
}
// метка категории: точка цвета --c + название
function catTag(cat, title) {
  const c = String(cat || "").toLowerCase();
  return `<span class="cat ${catClass(c)}"><i></i>${esc(title || CAT_TITLE[c] || cat || "—")}</span>`;
}
// пустое состояние (стр. 26): значок, заголовок, текст, кнопки
function emptyState({ icon = "blocks", tone = "", title, text = "", actions = "" }) {
  return `<div class="empty-state"><div class="es-ico ${tone}">${ICON[icon] || ""}</div><h2>${title}</h2>${text ? `<p>${text}</p>` : ""}${actions ? `<div class="row es-acts">${actions}</div>` : ""}</div>`;
}


// 1 день, 2 дня, 5 дней
function plural(n, one, few, many) {
  const a = Math.abs(n) % 100, b = a % 10;
  return a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many;
}

// уровень задачи (с сервера): кирпичик / блок / стена
function taskLevel(t) { return t?.level || "brick"; }
