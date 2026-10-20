// CODE RECALL — фронтенд без сборки. Роутинг по hash, по функции на экран.
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const view = $("#view");
const KINDS = ["imports", "class", "function", "train", "code", "main", "markdown"];
const MODES = { cells: "по ячейкам", gaps: "восстанови пропуск", scratch: "полностью с нуля" };  // «повторить блок» — кнопкой у блока

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
  t.innerHTML = (isErr ? '<span class="err">ERR</span> ' : "&gt; ") + esc(msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

const fmtMs = ms => {
  if (ms == null) return "—";
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};
const fmtDate = s => (s ? s.replace("T", " ").slice(0, 16) : "—");
const today = () => new Date().toISOString().slice(0, 10);

function editor(el, code, opts = {}) {
  return CodeMirror(el, {
    value: code, mode: "python", lineNumbers: true, indentUnit: 4, viewportMargin: Infinity,
    extraKeys: { Tab: cm => cm.somethingSelected() ? cm.execCommand("indentMore") : cm.replaceSelection("    "),
                 "Shift-Tab": cm => cm.execCommand("indentLess") },
    ...opts,
  });
}

function diffHtml(text) {
  if (!text) return '<span class="muted">нет различий</span>';
  return text.split("\n").map(l => {
    const cls = l.startsWith("+++") || l.startsWith("---") ? "muted" : l.startsWith("+") ? "ok"
      : l.startsWith("-") ? "err" : l.startsWith("@@") ? "warn" : "muted";
    return `<span class="${cls}">${esc(l)}</span>`;
  }).join("\n");
}

// ---------------- CRT-эффект (переключатель в настройках) ----------------
// Новый ключ: старая версия сама сохраняла «on» при каждом открытии, его не подхватываем.
const CRT_KEY = "crt-v2";
function crtOn() { try { return localStorage.getItem(CRT_KEY) === "on"; } catch { return false; } }
function applyCrt(on, save = false) {
  document.body.classList.toggle("crt", on);
  if (save) try { localStorage.setItem(CRT_KEY, on ? "on" : "off"); } catch { /* приватный режим */ }
}
applyCrt(crtOn());

// Редкие пиксельные звёзды на фоне: квадратики 2–4px, часть очень медленно мерцает.
(function stars() {
  const box = document.querySelector(".stars");
  if (!box) return;
  const colors = ["#F2F0FA", "#F2F0FA", "#F2F0FA", "#A6F04A", "#7B5CFF"];
  const n = Math.round(Math.min(70, window.innerWidth * window.innerHeight / 22000));
  box.innerHTML = Array.from({ length: n }, () => {
    const size = [2, 2, 3, 4][Math.floor(Math.random() * 4)];
    const tw = Math.random() < 0.35;
    return `<i class="${tw ? "tw" : ""}" style="left:${(Math.random() * 100).toFixed(2)}%;top:${(Math.random() * 100).toFixed(2)}%;`
      + `width:${size}px;height:${size}px;background:${colors[Math.floor(Math.random() * colors.length)]};`
      + `--d:${(6 + Math.random() * 8).toFixed(1)}s;--delay:-${(Math.random() * 10).toFixed(1)}s"></i>`;
  }).join("");
})();

// ---------------- роутер ----------------
const routes = { today: viewToday, library: viewLibrary, ref: viewRef, attempt: viewAttempt,
                 stats: viewStats, settings: viewSettings };
let leaveHook = null;  // ноутбук сохраняет черновик при уходе со страницы

function route() {
  if (leaveHook) { leaveHook(); leaveHook = null; }
  const [name, ...args] = location.hash.replace(/^#\/?/, "").split("/");
  const fn = routes[name] || viewToday;
  const navKey = { ref: "library", attempt: "library" }[name] || name || "today";
  $$("nav a").forEach(a => a.classList.toggle("active", a.dataset.r === navKey));
  view.innerHTML = '<p class="muted cursor">загрузка</p>';
  const cwd = $("#cwd");
  if (cwd) cwd.textContent = "~/" + [name || "today", ...args].filter(Boolean).join("/");
  fn(...args).catch(e => { view.innerHTML = `<p class="err">ОШИБКА: ${esc(e.message)}</p>`; });
}
window.addEventListener("hashchange", route);
route();

// ---------------- СЕГОДНЯ / СТАТИСТИКА (этапы 4–5) ----------------
async function viewToday() {
  const t = await api("/api/today");
  const section = (key, title, cls, empty) => {
    const items = t[key];
    return `<fieldset class="box"><legend class="${cls}">${title}: ${items.length}</legend>
      ${items.length ? `<table class="today"><tbody>${items.map(r => `
        <tr>
          <td class="tdate ${cls}">${r.due_at || "—"}</td>
          <td><a href="#/ref/${r.id}">${esc(r.title)}</a> ${r.tag ? `<span class="muted">· ${esc(r.tag)}</span>` : ""}
            <div class="muted small">${esc(r.reason)}</div></td>
          <td class="nowrap">
            <select data-mode="${r.id}">${Object.entries(MODES).map(([k, v]) => `<option value="${k}" ${k === r.mode ? "selected" : ""}>${v}</option>`).join("")}</select>
            <button data-go="${r.id}" class="primary">начать</button>
          </td>
        </tr>`).join("")}</tbody></table>` : `<p class="muted">${empty}</p>`}
    </fieldset>`;
  };
  const total = t.overdue.length + t.due.length + t.blocks.length;
  view.innerHTML = `
    <p>&gt; ${total ? `на сегодня к повторению: <b>${total}</b>` : "на сегодня повторений нет"}${t.new.length ? ` · новых: ${t.new.length}` : ""}</p>
    ${section("overdue", "ПРОСРОЧЕНО", "err", "ничего не просрочено")}
    ${section("due", "НА СЕГОДНЯ", "warn", "на сегодня всё повторено")}
    <fieldset class="box"><legend class="${t.blocks.length ? "warn" : ""}">ОТДЕЛЬНЫЕ БЛОКИ: ${t.blocks.length}</legend>
      <p class="muted small">Подошёл срок не всего эталона, а только этих блоков. При повторе блока предыдущие ячейки эталона выполнятся сами.</p>
      ${t.blocks.length ? `<table class="today"><tbody>${t.blocks.map(b => `
        <tr>
          <td class="tdate ${b.overdue ? "err" : "warn"}">${b.due_at || "новый"}</td>
          <td><b>${esc(b.block)}</b> <span class="muted">· <a href="#/ref/${b.id}">${esc(b.title)}</a></span>
            <div class="muted small">${esc(b.reason)}</div></td>
          <td class="nowrap"><button class="primary" data-block="${b.id}:${b.index}">повторить блок</button></td>
        </tr>`).join("")}</tbody></table>` : '<p class="muted">отдельных блоков к повторению нет</p>'}
    </fieldset>
    ${section("new", "НОВЫЕ", "ok", 'новых нет — загрузите эталоны в <a href="#/library">библиотеку</a>')}
    ${t.upcoming.length ? section("upcoming", "БЛИЖАЙШИЕ 7 ДНЕЙ", "muted", "") : ""}
    <p class="muted small">Режим выбран автоматически: новый эталон — по ячейкам; после «нормально/легко» — режим сложнее, после «забыл» — проще.</p>`;
  $$("[data-block]").forEach(b => b.onclick = () => { const [rid, idx] = b.dataset.block.split(":"); repeatBlock(rid, +idx); });
  $$("[data-go]").forEach(b => b.onclick = async () => {
    const id = b.dataset.go;
    try {
      const a = await api("/api/attempts", { method: "POST", json: { reference_id: +id, mode: $(`[data-mode="${id}"]`).value } });
      location.hash = `#/attempt/${a.id}`;
    } catch (e) { toast(e.message, true); }
  });
}

async function viewStats(rid) {
  const st = await api("/api/stats");
  const refs = await api("/api/references");
  const tried = refs.filter(r => r.attempts > 0);
  const s = st.streak;
  const maxCount = Math.max(1, ...st.calendar.map(d => d.count));
  const rate = x => `${bar(x, 10)} ${Math.round(x * 100)}%`;
  view.innerHTML = `
    <div class="tiles">
      <div class="tile"><div class="muted">СЕРИЯ</div><div class="hero ${s.current ? "ok" : "muted"}">${s.current}</div>
        <div class="muted small">${s.current ? "дн. подряд" : "дней подряд — начните сегодня"}${s.current && !s.today_done ? ' · <span class="warn">сегодня ещё не занимались</span>' : ""}</div></div>
      <div class="tile"><div class="muted">ЛУЧШАЯ СЕРИЯ</div><div class="hero">${s.best}</div><div class="muted small">дн.</div></div>
      <div class="tile"><div class="muted">ПОПЫТОК</div><div class="hero">${st.attempts}</div><div class="muted small">сдано всего</div></div>
      <div class="tile"><div class="muted">АКТИВНЫХ ДНЕЙ</div><div class="hero">${st.days_active}</div><div class="muted small">эталонов: ${st.references}</div></div>
    </div>
    <fieldset class="box"><legend>12 НЕДЕЛЬ</legend>
      <div class="cal">${st.calendar.map(d => `<i style="--a:${d.count ? 0.3 + 0.7 * d.count / maxCount : 0}" class="${d.count ? "on" : ""}" title="${d.date}: попыток ${d.count}"></i>`).join("")}${'<i class="future" title="ещё впереди"></i>'.repeat((7 - st.calendar.length % 7) % 7)}</div>
      <div class="muted small mt">столбец = неделя (пн → вс) · ярче = больше попыток · наведите на день</div>
    </fieldset>
    <fieldset class="box"><legend>СЛАБЫЕ ТЕМЫ</legend>
      ${st.weak_tags.length ? `<div class="scroll-x"><table class="stack"><thead><tr><th>тема</th><th>попыток</th><th>ср. оценка</th><th>блоков с ошибками</th></tr></thead><tbody>
        ${st.weak_tags.map(t => `<tr><td data-label="тема">${esc(t.tag)}</td><td data-label="попыток">${t.attempts}</td><td data-label="ср. оценка">${t.avg_score}</td>
          <td data-label="блоков с ошибками" class="nowrap ${t.error_rate >= 0.5 ? "err" : t.error_rate > 0 ? "warn" : "ok"}">${rate(t.error_rate)} <span class="muted">(${t.errors}/${t.blocks})</span></td></tr>`).join("")}
      </tbody></table></div>` : '<p class="muted">данных пока нет — сдайте первые попытки</p>'}
    </fieldset>
    <fieldset class="box"><legend>СЛАБЫЕ БЛОКИ</legend>
      ${st.weak_blocks.length ? `<div class="scroll-x"><table class="stack"><thead><tr><th>блок</th><th>ошибок</th><th>ср. оценка</th><th>последняя ошибка</th></tr></thead><tbody>
        ${st.weak_blocks.map(b => `<tr class="link" data-ref="${b.reference_id}"><td data-label="блок" class="stack-title"><div>${esc(b.block)}</div><div class="weak-ref">эталон: ${esc(b.reference)}</div></td>
          <td data-label="ошибок" class="nowrap ${b.error_rate >= 0.5 ? "err" : "warn"}">${b.errors} из ${b.n}</td><td data-label="ср. оценка">${b.avg_score}</td>
          <td data-label="последняя ошибка" class="muted small" title="${esc(b.last_error)}">${esc(b.last_error)}</td></tr>`).join("")}
      </tbody></table></div>` : '<p class="muted">ошибок пока нет</p>'}
      <p class="muted small">блок «с ошибкой»: оценка ниже 70, код падает, тест не прошёл или судья сказал не «верно»</p>
    </fieldset>
    <fieldset class="box"><legend>ПРОГРЕСС ПО ЭТАЛОНУ</legend>
      ${tried.length ? `<select id="pick">${tried.map(r => `<option value="${r.id}" ${String(r.id) === String(rid) ? "selected" : ""}>${esc(r.title)}</option>`).join("")}</select>
        <div id="progress" class="mt"></div>` : '<p class="muted">ни одной сданной попытки</p>'}
    </fieldset>`;
  $$("tr[data-ref]").forEach(tr => tr.onclick = () => { location.hash = `#/ref/${tr.dataset.ref}`; });
  if (tried.length) {
    const show = async id => progressCharts($("#progress"), await api(`/api/references/${id}/attempts`));
    $("#pick").onchange = e => show(e.target.value);
    show($("#pick").value);
  }
}

// Два отдельных графика (оценка и время) вместо двух осей на одном.
function progressCharts(box, attempts) {
  const pts = attempts.filter(a => a.status === "submitted").reverse()
    .map((a, i) => ({ i: i + 1, date: fmtDate(a.started_at), score: a.score, ms: a.total_ms, mode: a.mode_name, grade: a.grade }));
  if (!pts.length) { box.innerHTML = '<p class="muted">сданных попыток нет</p>'; return; }
  box.innerHTML = `<div class="chart-title">оценка, 0–100</div><div class="chart" id="ch-score"></div>
    <div class="chart-title mt">время</div><div class="chart" id="ch-time"></div>
    <p class="muted small">по оси X — попытки по порядку; таблица с теми же данными — на вкладке «история попыток» эталона</p>`;
  const tip = p => `${p.date} · попытка ${p.i}<br>${p.mode} · оценка <b>${p.score ?? "—"}</b> · время <b>${fmtMs(p.ms)}</b>${p.grade ? ` · ${p.grade}` : ""}`;
  lineChart($("#ch-score", box), pts, { y: p => p.score ?? 0, max: 100, ticks: [0, 50, 100], fmt: v => v, tip });
  const maxMs = Math.max(...pts.map(p => p.ms));
  const step = maxMs > 20 * 60000 ? 10 * 60000 : maxMs > 6 * 60000 ? 5 * 60000 : 60000;
  const top = Math.ceil(maxMs / step) * step || step;
  lineChart($("#ch-time", box), pts, { y: p => p.ms, max: top, ticks: [0, top / 2, top], fmt: fmtMs, tip });
}

function lineChart(el, pts, o) {
  const H = 150, padL = 46, padR = 12, padT = 10, padB = 22;
  const draw = () => {
    const W = Math.max(280, el.clientWidth);
    const x = i => pts.length === 1 ? padL + (W - padL - padR) / 2 : padL + i * (W - padL - padR) / (pts.length - 1);
    const y = v => padT + (1 - v / o.max) * (H - padT - padB);
    const path = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(o.y(p)).toFixed(1)}`).join("");
    const every = Math.ceil(pts.length / 8);  // подписи X не чаще ~8 штук
    el.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="график">
      ${o.ticks.map(t => `<line x1="${padL}" x2="${W - padR}" y1="${y(t)}" y2="${y(t)}" class="grid"/>
        <text x="${padL - 6}" y="${y(t) + 4}" text-anchor="end" class="axis">${o.fmt(t)}</text>`).join("")}
      ${pts.map((p, i) => i % every === 0 || i === pts.length - 1 ? `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" class="axis">${p.i}</text>` : "").join("")}
      <path d="${path}" class="series"/>
      ${pts.map((p, i) => `<circle cx="${x(i)}" cy="${y(o.y(p))}" r="4" class="dot"/>`).join("")}
      <line class="cross" y1="${padT}" y2="${H - padB}" visibility="hidden"/>
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent" class="hit"/>
    </svg><div class="tip" hidden></div>`;
    const svg = $("svg", el), cross = $(".cross", el), tipEl = $(".tip", el), dots = $$(".dot", el);
    const move = e => {
      const r = svg.getBoundingClientRect(), mx = e.clientX - r.left;
      let best = 0;
      pts.forEach((p, i) => { if (Math.abs(x(i) - mx) < Math.abs(x(best) - mx)) best = i; });
      cross.setAttribute("x1", x(best)); cross.setAttribute("x2", x(best)); cross.setAttribute("visibility", "visible");
      dots.forEach((d, i) => d.classList.toggle("hot", i === best));
      tipEl.hidden = false; tipEl.innerHTML = o.tip(pts[best]);
      const left = Math.min(Math.max(0, x(best) - tipEl.offsetWidth / 2), W - tipEl.offsetWidth);
      tipEl.style.left = left + "px"; tipEl.style.top = Math.max(0, y(o.y(pts[best])) - tipEl.offsetHeight - 10) + "px";
    };
    const leave = () => { cross.setAttribute("visibility", "hidden"); tipEl.hidden = true; dots.forEach(d => d.classList.remove("hot")); };
    $(".hit", el).addEventListener("pointermove", move);
    $(".hit", el).addEventListener("pointerleave", leave);
  };
  draw();
  new ResizeObserver(() => { if (Math.abs(el.clientWidth - ($("svg", el)?.getAttribute("width") || 0)) > 4) draw(); }).observe(el);
}

// ---------------- БИБЛИОТЕКА ----------------
const libState = { sort: "due_at", dir: 1, q: "", tag: "", due: "" };

function dueBucket(r) {
  if (!r.due_at) return "new";
  const d = r.due_at.slice(0, 10), t = today();
  if (d <= t) return "due";
  const week = new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 10);
  return d <= week ? "week" : "later";
}

async function viewLibrary() {
  const refs = await api("/api/references");
  const tags = [...new Set(refs.map(r => r.tag).filter(Boolean))].sort();
  const cols = [["title", "название"], ["tag", "тема"], ["blocks", "блоков"], ["last_attempt", "последняя попытка"],
                ["best_score", "лучшая оценка"], ["best_time_ms", "лучшее время"], ["due_at", "повторение"]];
  view.innerHTML = `
    <fieldset class="box"><legend>ЗАГРУЗКА</legend>
      <div class="drop" id="drop">&gt;&gt; перетащите .py / .ipynb или целые папки сюда &lt;&lt;</div>
      <div class="row mt"><button id="pick-files">выбрать файлы</button><button id="pick-dir">выбрать папку</button>
        <span class="muted small">из папки берутся все .py / .ipynb во вложенных папках; имя эталона = путь внутри папки</span></div>
      <input type="file" id="file" multiple accept=".py,.ipynb" hidden>
      <input type="file" id="dir" webkitdirectory multiple hidden>
      <div id="preview"></div>
    </fieldset>
    <fieldset class="box"><legend>ЭТАЛОНЫ: ${refs.length}</legend>
      <div class="row" style="margin-bottom:8px">
        <input id="q" placeholder="поиск" value="${esc(libState.q)}">
        <select id="tag"><option value="">все темы</option>${tags.map(t => `<option ${t === libState.tag ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
        <select id="due">${[["", "любая дата"], ["due", "на сегодня и просрочено"], ["week", "в ближайшие 7 дней"], ["new", "новые"], ["later", "позже"]]
          .map(([v, n]) => `<option value="${v}" ${v === libState.due ? "selected" : ""}>${n}</option>`).join("")}</select>
      </div>
      <div class="scroll-x"><table class="stack">
        <thead><tr>${cols.map(([k, n]) => `<th class="sort" data-k="${k}">${n}${libState.sort === k ? (libState.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
        <tbody id="rows"></tbody>
      </table></div>
      ${refs.length ? "" : '<p class="muted">пусто. загрузите первые файлы выше.</p>'}
    </fieldset>`;

  const renderRows = () => {
    const { q, tag, due, sort, dir } = libState;
    const rows = refs
      .filter(r => (!tag || r.tag === tag) && (!due || dueBucket(r) === due || (due === "week" && dueBucket(r) === "due"))
        && (r.title + r.filename).toLowerCase().includes(q.toLowerCase()))
      .sort((a, b) => {
        // Пустые значения всегда внизу; новые эталоны (без даты) — первыми при сортировке по повторению.
        let x = a[sort], y = b[sort];
        if (sort === "due_at") { x = x ?? ""; y = y ?? ""; }
        if (x == null) return 1; if (y == null) return -1;
        return (typeof x === "string" ? x.localeCompare(y) : x - y) * dir;
      });
    $("#rows").innerHTML = rows.map(r => {
      const b = dueBucket(r);
      const due = b === "new" ? '<span class="ok">новый</span>'
        : `<span class="${b === "due" ? "warn" : ""}">${r.due_at.slice(0, 10)}</span>`;
      return `<tr class="link" data-id="${r.id}">
        <td data-label="название" class="stack-title">${esc(r.title)}${r.orphan_tests ? ` <span class="warn" title="тесты без блока">⚠${r.orphan_tests}</span>` : ""}</td>
        <td data-label="тема">${esc(r.tag) || '<span class="muted">—</span>'}</td>
        <td data-label="блоков">${r.blocks}</td>
        <td data-label="последняя попытка">${fmtDate(r.last_attempt)}</td>
        <td data-label="лучшая оценка">${r.best_score ?? "—"}</td>
        <td data-label="лучшее время">${fmtMs(r.best_time_ms)}</td>
        <td data-label="повторение">${due}</td></tr>`;
    }).join("");
  };
  renderRows();
  $("#q").oninput = e => { libState.q = e.target.value; renderRows(); };
  $("#tag").onchange = e => { libState.tag = e.target.value; renderRows(); };
  $("#due").onchange = e => { libState.due = e.target.value; renderRows(); };
  $$("th.sort").forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    libState.dir = libState.sort === k ? -libState.dir : 1;
    libState.sort = k;
    viewLibrary();
  });
  $("#rows").onclick = e => {
    const tr = e.target.closest("tr[data-id]");
    if (tr) location.hash = `#/ref/${tr.dataset.id}`;
  };

  const drop = $("#drop"), input = $("#file"), dir = $("#dir");
  drop.onclick = $("#pick-files").onclick = () => input.click();
  $("#pick-dir").onclick = () => dir.click();
  input.onchange = () => previewUpload([...input.files].map(f => ({ file: f, path: "" })));
  // webkitRelativePath = "папка/под/файл.py" -> путь без корневой папки
  dir.onchange = () => previewUpload([...dir.files].map(f => ({ file: f, path: f.webkitRelativePath.split("/").slice(1).join("/") })));
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = async e => {
    e.preventDefault(); drop.classList.remove("over");
    const entries = [...e.dataTransfer.items].map(it => it.webkitGetAsEntry && it.webkitGetAsEntry()).filter(Boolean);
    const items = entries.length ? await collectEntries(entries) : [...e.dataTransfer.files].map(f => ({ file: f, path: "" }));
    previewUpload(items);
  };
}

const SKIP_DIRS = /(^|\/)(\.[^/]*|__pycache__|\.ipynb_checkpoints|venv|\.venv|env|site-packages|node_modules)(\/|$)/;
const isCode = path => /\.(py|ipynb)$/i.test(path) && !SKIP_DIRS.test(path);

// Рекурсивный обход перетащенных папок (File System Entry API).
async function collectEntries(entries) {
  const out = [];
  const fileOf = en => new Promise((res, rej) => en.file(res, rej));
  const readAll = async reader => {  // readEntries отдаёт пачками по ~100
    const all = [];
    for (;;) {
      const batch = await new Promise((res, rej) => reader.readEntries(res, rej));
      if (!batch.length) return all;
      all.push(...batch);
    }
  };
  async function walk(en, root) {
    if (en.isFile) {
      // путь без корневой перетащенной папки; отдельный файл — просто имя
      const rel = root ? en.fullPath.slice(root.length + 2) : "";
      if (isCode(rel || en.name)) out.push({ file: await fileOf(en), path: rel });
    } else if (en.isDirectory && !(root && SKIP_DIRS.test(en.name))) {
      for (const child of await readAll(en.createReader())) await walk(child, root ?? en.name);
    }
  }
  for (const en of entries) await walk(en, null);
  return out;
}

// Шаг 1: предпросмотр (ничего не сохраняется). Шаг 2: сохраняем отмеченные.
async function previewUpload(items) {
  const box = $("#preview");
  items = items.filter(it => isCode(it.path || it.file.name));
  if (!items.length) { box.innerHTML = '<p class="warn">нет файлов .py / .ipynb</p>'; return; }
  box.innerHTML = `<p class="cursor">разбираю ${items.length} файл(ов)</p>`;
  const form = list => {
    const fd = new FormData();
    list.forEach(it => { fd.append("files", it.file); fd.append("paths", it.path || ""); });
    return fd;
  };
  const fd = form(items);
  let res;
  try { res = await api("/api/upload/preview", { method: "POST", body: fd }); }
  catch (e) { box.innerHTML = `<p class="err">ОШИБКА: ${esc(e.message)}</p>`; return; }

  const label = { new: ["ok", "НОВЫЙ"], changed: ["warn", "ИЗМЕНЁН"], unchanged: ["muted", "БЕЗ ИЗМЕНЕНИЙ"],
                  skipped: ["err", "ПРОПУЩЕН"], error: ["err", "ОШИБКА"] };
  const html = res.map((r, i) => {
    const [cls, txt] = label[r.status];
    const canSave = r.status === "new" || r.status === "changed";
    let extra = "";
    if (r.status === "new") extra = `<span class="muted"> — ${r.blocks} блок(ов)</span>`;
    if (r.error) extra = ` — ${esc(r.error)}`;
    if (r.status === "changed") {
      const b = r.blocks;
      extra = ` <span class="muted">→ «${esc(r.title)}» v${r.version} → v${r.version + 1}</span>
        <div class="sub">
          ${b.added.length ? `<div class="ok">+ новые блоки: ${b.added.map(esc).join(", ")}</div>` : ""}
          ${b.removed.length ? `<div class="err">- пропадут блоки: ${b.removed.map(esc).join(", ")}</div>` : ""}
          ${b.changed.length ? `<div class="warn">~ изменены: ${b.changed.map(esc).join(", ")}</div>` : ""}
          ${b.orphaned_tests.length ? `<div class="warn">⚠ тесты останутся без блока (привяжете вручную): ${b.orphaned_tests.map(esc).join(", ")}</div>` : ""}
          ${b.progress_reset.length ? `<div class="warn">↺ прогресс повторений начнётся заново для: ${b.progress_reset.map(esc).join(", ")}</div>` : ""}
          ${b.same.length ? `<div class="muted">= прогресс сохранится: ${b.same.map(esc).join(", ")}</div>` : ""}
          <details><summary>diff</summary><pre class="src diff">${diffHtml(r.diff)}</pre></details>
        </div>`;
    }
    return `<div class="pv ${canSave ? "" : "quiet"}"><label><input type="checkbox" data-i="${i}" ${canSave ? "checked" : "disabled"}>
      <span class="${cls}">[${txt}]</span> ${esc(r.filename)}</label>${extra}</div>`;
  });
  const count = st => res.filter(r => r.status === st).length;
  const rows = res.map((r, i) => [r, html[i]]);
  const quiet = rows.filter(([r]) => r.status === "unchanged");
  box.innerHTML = `
    <p class="mt">всего ${res.length}: <span class="ok">новых ${count("new")}</span> · <span class="warn">изменённых ${count("changed")}</span>
      · <span class="muted">без изменений ${count("unchanged")}</span>${count("error") + count("skipped") ? ` · <span class="err">ошибок ${count("error") + count("skipped")}</span>` : ""}</p>
    <div>${rows.filter(([r]) => r.status !== "unchanged").map(x => x[1]).join("")}</div>
    ${quiet.length ? `<details><summary>без изменений: ${quiet.length}</summary>${quiet.map(x => x[1]).join("")}</details>` : ""}
    <div class="row mt"><button id="commit" class="primary">сохранить отмеченные</button><button id="cancel">отмена</button></div>`;

  $("#cancel").onclick = () => { box.innerHTML = ""; };
  $("#commit").onclick = async () => {
    // ответ сервера идёт в том же порядке, что и файлы
    const chosen = $$("input[data-i]:checked", box).map(c => items[+c.dataset.i]);
    if (!chosen.length) return toast("ничего не отмечено", true);
    try {
      const out = await api("/api/upload", { method: "POST", body: form(chosen) });
      toast(`сохранено: ${out.filter(o => o.status !== "unchanged").length}`);
      viewLibrary();
    } catch (e) { toast(e.message, true); }
  };
}

// ---------------- ЭТАЛОН ----------------
const REF_TABS = [["blocks", "ноутбук"], ["split", "изменить разбиение"], ["tests", "тесты"],
                  ["versions", "история версий"], ["attempts", "история попыток"]];

async function viewRef(id, tab = "blocks", arg) {
  const ref = await api(`/api/references/${id}`);
  view.innerHTML = `
    <p><a href="#/library">&lt; библиотека</a></p>
    <fieldset class="box"><legend>${esc(ref.title)}</legend>
      <div class="row">
        <span class="muted">файл:</span> ${esc(ref.filename)}
        <span class="muted">v${ref.version} · ${ref.blocks} блоков кода · ${ref.tests} тестов</span>
        ${ref.orphan_tests ? `<a class="warn" href="#/ref/${id}/tests">⚠ ${ref.orphan_tests} без блока</a>` : ""}
        <span class="grow"></span>
        <select id="mode">${Object.entries(MODES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        <button id="start" class="primary">начать задание</button>
      </div>
      <details class="mt"><summary>свойства</summary>
        <div class="row mt">
          <label>название</label><input id="m-title" class="grow" value="${esc(ref.title)}">
          <label>тема</label><input id="m-tag" value="${esc(ref.tag)}" placeholder="CNN, алгоритмы…">
          <label>сложность</label>
          <select id="m-diff">${[1, 2, 3, 4, 5].map(n => `<option ${n === ref.difficulty ? "selected" : ""}>${n}</option>`).join("")}</select>
        </div>
        <div class="mt"><label>задача «с нуля» (словами, без кода)</label><textarea id="m-task">${esc(ref.task)}</textarea></div>
        <div class="mt"><label>заметки</label><textarea id="m-notes">${esc(ref.notes)}</textarea></div>
        <div class="row mt">
          <button id="m-save" class="primary">сохранить</button>
          <button id="m-describe">описания через LLM</button>
          <span class="grow"></span>
          <button class="danger" id="m-del">удалить эталон</button>
        </div>
      </details>
    </fieldset>
    <nav class="tabs">${REF_TABS.map(([k, n]) => `<a href="#/ref/${id}/${k}" class="${k === tab ? "active" : ""}">${n}</a>`).join("")}</nav>
    <div id="tab"></div>
    <div id="ws"></div>`;

  $("#start").onclick = async () => {
    try {
      const a = await api("/api/attempts", { method: "POST", json: { reference_id: +id, mode: $("#mode").value } });
      location.hash = `#/attempt/${a.id}`;
    } catch (e) { toast(e.message, true); }
  };
  $("#m-save").onclick = async () => {
    try {
      await api(`/api/references/${id}`, { method: "PATCH", json: {
        title: $("#m-title").value, tag: $("#m-tag").value.trim(), difficulty: +$("#m-diff").value,
        task: $("#m-task").value, notes: $("#m-notes").value } });
      toast("сохранено");
    } catch (e) { toast(e.message, true); }
  };
  $("#m-describe").onclick = async e => {
    const over = confirm("Перезаписать уже заполненные описания?\nОК — перезаписать, Отмена — только пустые.");
    e.target.disabled = true; e.target.textContent = "думаю…";
    try {
      await api(`/api/references/${id}/describe?overwrite=${over}`, { method: "POST" });
      toast("описания готовы"); viewRef(id, tab);
    } catch (err) { toast(err.message, true); e.target.disabled = false; e.target.textContent = "описания через LLM"; }
  };
  $("#m-del").onclick = async () => {
    if (!confirm(`Удалить «${ref.title}» со всеми версиями, тестами и попытками?`)) return;
    await api(`/api/references/${id}`, { method: "DELETE" });
    location.hash = "#/library";
  };

  const tabs = { blocks: tabBlocks, split: tabSplit, tests: tabTests, versions: tabVersions, attempts: tabAttempts };
  await (tabs[tab] || tabBlocks)(ref, $("#tab"), arg);
  workspacePanel(ref, $("#ws"));
}

// ---------------- папка эталона (внизу страницы) ----------------
const FILE_ICON = { dir: "▸", image: "▣", video: "▶", audio: "♪", text: "≡", file: "·", broken: "⚠" };
const fmtSize = b => b == null ? "" : b < 1024 ? `${b} Б` : b < 1048576 ? `${(b / 1024).toFixed(0)} КБ` : `${(b / 1048576).toFixed(1)} МБ`;

async function workspacePanel(ref, box) {
  const info = await api(`/api/references/${ref.id}/workspace`);
  let target = "data";  // куда загружать файлы
  box.innerHTML = `
    <fieldset class="box"><legend>ПАПКА ЭТАЛОНА</legend>
      <p class="muted small">Рабочая папка ядра — <code>${esc(info.path)}</code>. Пути в коде пишите относительно неё:
        <code>pd.read_csv("data/x.csv")</code>, <code>plt.savefig("results/fig.png")</code>.
        Попытки сохраняют файлы в <code>results/attempts/&lt;id&gt;/</code>, чтобы не перезатирать файлы эталона.</p>
      <div class="ws-grid">
        <div>
          <div class="label">ОКРУЖЕНИЕ PYTHON</div>
          <div class="row"><input id="py" class="grow" placeholder="по умолчанию — окружение приложения; путь к .venv или папке проекта" value="${esc(info.python)}">
            <button id="py-check">проверить</button><button id="py-save" class="primary">сохранить</button></div>
          <div id="py-out" class="small mt muted">сейчас: <code>${esc(info.python_resolved)}</code></div>
        </div>
        <div>
          <div class="label">ДАННЫЕ (data/)</div>
          ${info.data_link ? `<div class="small">привязана папка <code>${esc(info.data_link)}</code> — файлы не копируются</div>
              <div class="row mt"><button id="unbind">отвязать</button></div>`
            : `<div class="row"><input id="bind-path" class="grow" placeholder="/путь/к/папке/с/датасетом">
              <button id="bind">привязать как data/</button></div>
              <div class="small muted mt">большие датасеты не копируются: data/ станет ссылкой на эту папку</div>`}
        </div>
      </div>
      <div class="row mt">
        <span class="label">ФАЙЛЫ</span><span class="grow"></span>
        <span class="small muted">загрузить в <b id="target">data/</b></span>
        <button id="up">загрузить…</button><input type="file" id="up-file" multiple hidden>
        <button id="refresh" title="обновить">↻</button>
      </div>
      <div class="ws-files">
        <div id="tree" class="tree"></div>
        <div id="pv" class="pv-file muted small">выберите файл, чтобы посмотреть</div>
      </div>
    </fieldset>`;

  const pyOut = $("#py-out", box);
  const showPy = r => {
    pyOut.className = "small mt";
    pyOut.innerHTML = `<code>${esc(r.python)}</code> · Python ${esc(r.version)} · пакеты: ${r.packages.map(esc).join(", ") || "—"}`
      + (r.ipykernel ? ' · <span class="ok">ipykernel есть</span>' : `<div class="err mt">нет ipykernel — ядро не запустится. Установите: <code>${esc(r.fix)}</code></div>`);
  };
  $("#py-check", box).onclick = async () => {
    try { showPy(await api("/api/python/check", { method: "POST", json: { path: $("#py", box).value.trim() } })); }
    catch (e) { pyOut.className = "small mt err"; pyOut.textContent = e.message; }
  };
  $("#py-save", box).onclick = async () => {
    try {
      await api(`/api/references/${ref.id}`, { method: "PATCH", json: { python: $("#py", box).value.trim() } });
      toast("окружение сохранено — ядро эталона перезапустится в нём"); viewRef(ref.id, location.hash.split("/")[3] || "blocks");
    } catch (e) { pyOut.className = "small mt err"; pyOut.textContent = e.message; }
  };
  const bindBtn = $("#bind", box), unbindBtn = $("#unbind", box);
  if (bindBtn) bindBtn.onclick = async () => {
    try { await api(`/api/references/${ref.id}/data/bind`, { method: "POST", json: { path: $("#bind-path", box).value.trim() } }); toast("папка привязана"); workspacePanel(ref, box); }
    catch (e) { toast(e.message, true); }
  };
  if (unbindBtn) unbindBtn.onclick = async () => {
    if (!confirm("Отвязать папку? Удалится только ссылка, ваши файлы останутся на месте.")) return;
    await api(`/api/references/${ref.id}/data/unbind`, { method: "POST" }); workspacePanel(ref, box);
  };

  const tree = $("#tree", box), pv = $("#pv", box);
  async function renderDir(el, path, depth) {
    let items;
    try { items = await api(`/api/references/${ref.id}/files?path=${encodeURIComponent(path)}`); }
    catch (e) { el.innerHTML = `<div class="err small">${esc(e.message)}</div>`; return; }
    el.innerHTML = items.length ? "" : `<div class="muted small" style="padding-left:${depth * 16 + 22}px">пусто</div>`;
    for (const it of items) {
      const row = document.createElement("div");
      row.className = "trow";
      row.style.paddingLeft = depth * 16 + "px";
      const raw = `/api/references/${ref.id}/raw/${it.path.split("/").map(encodeURIComponent).join("/")}`;
      row.innerHTML = `<span class="ticon ${it.kind}">${FILE_ICON[it.kind] || "·"}</span>
        <span class="tname">${esc(it.name)}${it.link ? ` <span class="muted small">→ ${esc(it.link)}</span>` : ""}</span>
        <span class="tsize muted small">${fmtSize(it.size)}</span>
        <span class="tact">${it.dir ? `<button class="small raw" data-to title="загружать сюда">⇪</button>` : `<a class="small" href="${raw}?download=1" title="скачать">⇩</a>`}
          <button class="small raw danger" data-del title="удалить">✕</button></span>`;
      el.appendChild(row);
      const kids = document.createElement("div");
      kids.hidden = true;
      el.appendChild(kids);
      row.onclick = async e => {
        if (e.target.closest("[data-del],[data-to],a")) return;
        if (it.dir) {
          kids.hidden = !kids.hidden;
          row.querySelector(".ticon").textContent = kids.hidden ? "▸" : "▾";
          if (!kids.hidden && !kids.dataset.loaded) { kids.dataset.loaded = 1; await renderDir(kids, it.path, depth + 1); }
        } else preview(it, raw);
        $$(".trow.sel", tree).forEach(r => r.classList.remove("sel")); row.classList.add("sel");
      };
      const to = $("[data-to]", row);
      if (to) to.onclick = () => { target = it.path; $("#target", box).textContent = it.path + "/"; };
      $("[data-del]", row).onclick = async () => {
        const inData = it.path === "data" || it.path.startsWith("data/");
        if (!confirm(`Удалить ${it.path}?` + (inData && info.data_link ? "\nВНИМАНИЕ: data/ привязана к вашей папке — файл удалится с диска." : ""))) return;
        try { await api(`/api/references/${ref.id}/files?path=${encodeURIComponent(it.path)}`, { method: "DELETE" }); row.remove(); kids.remove(); }
        catch (err) { toast(err.message, true); }
      };
    }
  }
  async function preview(it, raw) {
    const name = `<div class="pv-head"><b>${esc(it.name)}</b> <span class="muted">${fmtSize(it.size)}</span> <a href="${raw}?download=1">скачать</a></div>`;
    if (it.kind === "image") pv.innerHTML = name + `<img src="${raw}" alt="${esc(it.name)}">`;
    else if (it.kind === "video") pv.innerHTML = name + `<video src="${raw}" controls></video>`;
    else if (it.kind === "audio") pv.innerHTML = name + `<audio src="${raw}" controls></audio>`;
    else if (it.kind === "text" && it.size < 400000) {
      const text = await fetch(raw).then(r => r.text());
      pv.innerHTML = name + (it.name.endsWith(".md") ? `<div class="md"></div>` : `<pre class="src">${esc(text.slice(0, 200000))}</pre>`);
      if (it.name.endsWith(".md")) mdInto($(".md", pv), text);
    } else pv.innerHTML = name + '<p class="muted">просмотр недоступен — скачайте файл</p>';
    pv.className = "pv-file";
  }
  const reload = () => renderDir(tree, "", 0);
  $("#refresh", box).onclick = reload;
  $("#up", box).onclick = () => $("#up-file", box).click();
  $("#up-file", box).onchange = async e => {
    const fd = new FormData();
    [...e.target.files].forEach(f => fd.append("files", f));
    fd.append("folder", target);
    try { const r = await api(`/api/references/${ref.id}/files`, { method: "POST", body: fd }); toast(`загружено: ${r.saved.length}`); reload(); }
    catch (err) { toast(err.message, true); }
    e.target.value = "";
  };
  reload();
}

async function repeatBlock(refId, index) {
  try {
    const a = await api("/api/attempts", { method: "POST", json: { reference_id: +refId, mode: "block", block: index } });
    location.hash = `#/attempt/${a.id}`;
  } catch (e) { toast(e.message, true); }
}

function testsByBlock(ref) {
  const m = {};
  ref.test_list.forEach(t => { (m[t.block] ||= []).push(t); });
  return m;
}

function testLine(t) {
  return `<div class="test"><span class="${t.orphan ? "warn" : "muted"}">${t.orphan ? "⚠ без блока" : t.mode === "assert" ? "assert" : "= эталон"}</span>
    ${t.broken ? '<span class="err">[сломан]</span>' : ""}
    ${t.approved ? "" : '<span class="warn">[не подтверждён]</span>'} ${esc(t.name || "без названия")}
    <code class="muted">${esc(t.code.split("\n")[0])}</code></div>`;
}

function blockState(st) {
  if (!st || st.status === "new") return '<span class="ok">● ещё не повторялся</span>';
  return `<span class="muted">повторение</span> ${st.due.slice(0, 10)} <span class="muted">· повторений ${st.reps} · последний уровень</span> ${{ 1: "забыл", 2: "трудно", 3: "нормально", 4: "легко" }[st.last_grade]}`;
}

// Вкладка «ноутбук»: эталон как в Jupyter — markdown отрисован, код можно запускать
// (ядро эталона, рабочая папка = папка эталона). Код здесь не редактируется — для этого «изменить разбиение».
// Ядро не гасится при переключении вкладок (само выключится через 15 мин простоя или кнопкой),
// а выводы и идущие ячейки сохраняются в NB_STATE — вернулись на вкладку, всё на месте.
const NB_STATE = {};

async function tabBlocks(ref, box) {
  const tests = testsByBlock(ref);
  const sk = `${ref.id}:${ref.shown_version.id}`;
  const st = NB_STATE[sk] ||= {
    cells: ref.shown_version.cells.map(c => ({ ...c, outputs: [], count: null, running: false })),
    kc: new KernelClient(`r${ref.id}`), sel: -1, els: [],
  };
  const { cells, kc } = st;
  let heavy = new Set(ref.heavy), caches = ref.caches;
  if (st.sel < 0) st.sel = cells.findIndex(c => c.kind !== "markdown");
  box.innerHTML = `
    <div class="nb-sticky"><div id="tb"></div></div>
    <p class="muted small">Ячейки выполняются в ядре эталона: рабочая папка — папка эталона (data/, results/), окружение —
      ${ref.python ? `<code>${esc(ref.python)}</code>` : "окружение приложения"} (меняется внизу страницы).
      Ядро работает, пока вы переключаете вкладки, и выключается само после 15 минут простоя.
      <b>Тяжёлый</b> блок (обучение, большие данные) при «повторить блок» не пересчитывается: после запуска здесь его переменные сохраняются в кэш.</p>
    <div id="nb"></div>
    ${tests[""] ? `<fieldset class="box"><legend>тесты на весь код</legend>${tests[""].map(testLine).join("")}</fieldset>` : ""}`;
  const bar = toolbar($("#tb", box), [TB.run, TB.runAll, "|", TB.clear, TB.stop, TB.restart, TB.off], {
    run: () => runCell(st.sel, true),
    runAll: async () => { for (let i = 0; i < cells.length; i++) if (cells[i].kind !== "markdown" && !(await runCell(i))) break; },
    clear: () => { cells.forEach((c, i) => { c.outputs = []; c.count = null; paint(i); }); },
    stop: () => kc.interrupt(),
    restart: async () => {
      if (!confirm("Перезапустить ядро? Все переменные пропадут.")) return;
      bar.setKernel("restarting"); await kc.restart(); cells.forEach(c => { c.count = null; }); cells.forEach((_, i) => paint(i)); refreshKernel();
    },
    off: async () => { await kc.stop(); cells.forEach(c => { c.count = null; }); cells.forEach((_, i) => paint(i)); refreshKernel(); },
  });
  const refreshKernel = () => api(`/api/kernels/r${ref.id}/state`).then(r => {
    bar.setKernel(r.kernel);
    const k = $("[data-kstate]", box);
    if (k && r.idle_left != null && r.kernel === "idle") k.title = `выключится через ${Math.ceil(r.idle_left / 60)} мин простоя`;
  }).catch(() => {});
  refreshKernel();

  const list = $("#nb", box);
  const fmtEst = ms => (ms == null ? "" : ms < 1000 ? "<1 с" : fmtMs(ms));
  function heavyInfo(c) {
    const t = ref.block_times[c.title];
    const time = t != null ? `<span class="muted small" title="время последнего запуска кода эталона">⏱ ${fmtEst(t)}</span>` : "";
    if (!heavy.has(c.title)) return time;
    const ch = caches[c.title];
    const cacheTxt = !ch || !ch.exists ? '<span class="warn small">кэша нет — запустите блок</span>'
      : ch.valid ? `<span class="ok small" title="${esc((ch.names || []).join(", "))}">💾 кэш ${fmtSize(ch.size)} · ${esc(ch.created || "")}</span>`
        : '<span class="warn small">кэш устарел — код или окружение изменились</span>';
    return `${time} ${cacheTxt}`;
  }
  st.els = cells.map((c, i) => {
    const el = document.createElement("div");
    el.className = "nbcell" + (c.kind === "markdown" ? " is-md" : "");
    el.onclick = () => select(i);
    list.appendChild(el);  // до создания редактора: CodeMirror меряет размеры в документе
    if (c.kind === "markdown") {
      el.innerHTML = `<div class="md"></div>`;
      mdInto($(".md", el), c.code);
    } else {
      const prev = cells[i - 1];
      const dupDesc = prev && prev.kind === "markdown" && prev.code.trim() === (c.description || "").trim();
      const bt = tests[c.title] || [];
      el.innerHTML = `
        <div class="cellhead">
          <span class="prompt" data-count>[ ]</span>
          <b>${esc(c.title)}</b> <span class="muted small">${c.kind}</span>
          <span class="small">${blockState(ref.block_states[c.title])}</span>
          <span data-heavyinfo>${heavyInfo(c)}</span>
          <span class="grow"></span>
          <label class="small heavy-toggle" title="при «повторить блок» не выполнять заново, а загрузить кэш"><input type="checkbox" data-heavy ${heavy.has(c.title) ? "checked" : ""}> тяжёлый</label>
          <button class="small" data-run title="запустить (Shift+Enter)">▶</button>
          <button class="small" data-repeat title="повторить только этот блок: предыдущие выполнятся сами">повторить</button>
        </div>
        ${c.description && !dupDesc ? `<div class="md desc-md small"></div>` : ""}
        <div class="ed"></div>
        <div class="outs"></div>
        ${bt.length ? `<details class="small"><summary>тесты: ${bt.length}</summary>${bt.map(testLine).join("")}</details>` : ""}`;
      if (c.description && !dupDesc) mdInto($(".desc-md", el), c.description);
      $("[data-run]", el).onclick = e => { e.stopPropagation(); runCell(i); };
      $("[data-repeat]", el).onclick = e => { e.stopPropagation(); repeatBlock(ref.id, i); };
      $("[data-heavy]", el).onclick = e => e.stopPropagation();
      $("[data-heavy]", el).onchange = async e => {
        try {
          const r = await api(`/api/references/${ref.id}/heavy`, { method: "POST", json: { title: c.title, heavy: e.target.checked } });
          heavy = new Set(r.heavy); caches = r.caches;
          $("[data-heavyinfo]", el).innerHTML = heavyInfo(c);
          toast(e.target.checked ? "тяжёлый: запустите блок, чтобы сохранить кэш" : "блок больше не тяжёлый");
        } catch (err) { toast(err.message, true); }
      };
      const cm = editor($(".ed", el), c.code, { readOnly: true, extraKeys: {
        "Shift-Enter": () => runCell(i, true), "Ctrl-Enter": () => runCell(i), "Cmd-Enter": () => runCell(i) } });
      cm.on("focus", () => select(i));
      c.cm = cm;
    }
    return el;
  });
  cells.forEach((_, i) => paint(i));

  function select(i) { st.sel = i; st.els.forEach((e, k) => e.classList.toggle("sel", k === i)); }
  function paint(i) {
    const c = cells[i], el = st.els[i];
    if (c.kind === "markdown" || !el || !document.body.contains(el)) return;
    $("[data-count]", el).textContent = c.running ? "[*]" : `[${c.count ?? " "}]`;
    renderOutputs($(".outs", el), c.outputs, { refId: ref.id });
  }
  async function runCell(i, advance = false) {
    if (i < 0 || i >= cells.length) return true;
    const c = cells[i];
    if (advance) {
      const next = cells.findIndex((x, k) => k > i && x.kind !== "markdown");
      if (next >= 0) { select(next); cells[next].cm.focus(); st.els[next].scrollIntoView({ block: "nearest" }); }
    }
    if (c.kind === "markdown") return true;
    c.running = true; c.outputs = []; paint(i); bar.setKernel("busy");
    try {
      // block — сервер запомнит время запуска, а у тяжёлого блока сохранит кэш
      const r = await kc.run(c.code, outs => { c.outputs = outs; paint(i); }, { block: c.title });
      c.outputs = r.outputs; c.count = r.count;
    } catch (e) { c.outputs = [{ type: "error", ename: "Ошибка", evalue: e.message }]; }
    c.running = false; paint(i);
    if (document.body.contains(box)) {
      refreshKernel();
      const fresh = await api(`/api/references/${ref.id}`).catch(() => null);  // время и кэш обновились
      if (fresh) { ref.block_times = fresh.block_times; caches = fresh.caches; const hi = $("[data-heavyinfo]", st.els[i]); if (hi) hi.innerHTML = heavyInfo(c); }
    }
    return !c.outputs.some(o => o.type === "error");
  }
  select(st.sel);
}

async function tabSplit(ref, box) {
  let cells = ref.shown_version.cells.map(c => ({ ...c }));
  let editors = [], dirty = false;
  box.innerHTML = `
    <fieldset class="box"><legend>РАЗБИЕНИЕ · v${ref.version}</legend>
      <div class="row" style="margin-bottom:10px">
        <button id="split-ast">заново по AST</button>
        <button id="split-llm" ${ref.filename.endsWith(".py") ? "" : "disabled"}>заново через LLM</button>
        <button id="show-src">исходник</button>
        <span class="grow"></span>
        <span id="dirty" class="warn"></span>
        <button id="save-cells" class="primary">сохранить</button>
      </div>
      <p class="muted">Тесты привязаны к названию блока: при переименовании здесь они едут за блоком.</p>
      <pre class="src" id="src" hidden>${esc(ref.shown_version.source)}</pre>
      <div id="cells"></div>
      <button id="add-cell">+ блок</button>
    </fieldset>`;

  const markDirty = () => { dirty = true; $("#dirty").textContent = "* есть несохранённые изменения"; };
  const sync = () => editors.forEach((cm, i) => { cells[i].code = cm.getValue(); });

  function renderCells() {
    const list = $("#cells");
    list.innerHTML = "";
    editors = cells.map((c, i) => {
      const el = document.createElement("div");
      el.className = "cell";
      el.innerHTML = `
        <div class="head">
          <span class="num">[${String(i + 1).padStart(2, "0")}]</span>
          <select data-f="kind">${KINDS.map(k => `<option ${k === c.kind ? "selected" : ""}>${k}</option>`).join("")}</select>
          <input class="title" data-f="title" value="${esc(c.title)}" placeholder="название блока">
          <button class="small" data-a="up" title="выше">↑</button>
          <button class="small" data-a="down" title="ниже">↓</button>
          <button class="small" data-a="merge" title="слить со следующим">слить↓</button>
          <button class="small" data-a="cut" title="разрезать по строке курсора">разрезать</button>
          <button class="small danger" data-a="del" title="удалить">x</button>
        </div>
        ${c.kind === "markdown" ? "" : `<textarea class="desc" data-f="description" placeholder="описание словами (без кода)">${esc(c.description)}</textarea>`}`;
      list.appendChild(el);
      $$("[data-f]", el).forEach(inp => inp.oninput = () => { c[inp.dataset.f] = inp.value; markDirty(); });
      $$("[data-a]", el).forEach(b => b.onclick = () => cellAction(b.dataset.a, i));
      const isMd = c.kind === "markdown";
      const cm = editor(el, c.code, isMd ? { mode: "markdown", lineNumbers: false, lineWrapping: true } : {});
      cm.on("change", markDirty);
      if (isMd) {  // предпросмотр, как будет выглядеть ячейка
        const pv = document.createElement("div");
        pv.className = "md md-preview";
        el.appendChild(pv);
        mdInto(pv, c.code);
        let t;
        cm.on("change", () => { clearTimeout(t); t = setTimeout(() => mdInto(pv, cm.getValue()), 300); });
      }
      $("[data-f=kind]", el).onchange = e => { sync(); c.kind = e.target.value; markDirty(); renderCells(); };
      return cm;
    });
  }

  function cellAction(a, i) {
    sync();
    if (a === "up" && i > 0) [cells[i - 1], cells[i]] = [cells[i], cells[i - 1]];
    if (a === "down" && i < cells.length - 1) [cells[i + 1], cells[i]] = [cells[i], cells[i + 1]];
    if (a === "del" && confirm(`Удалить блок ${i + 1}?`)) cells.splice(i, 1);
    if (a === "merge" && i < cells.length - 1) {
      const n = cells[i + 1];
      cells[i].code += "\n\n" + n.code;
      cells[i].description = [cells[i].description, n.description].filter(Boolean).join("\n");
      cells.splice(i + 1, 1);
    }
    if (a === "cut") {
      const line = editors[i].getCursor().line;
      if (line === 0) return toast("поставьте курсор на строку, с которой начнётся новый блок", true);
      const lines = cells[i].code.split("\n");
      cells[i].code = lines.slice(0, line).join("\n").replace(/\s+$/, "");
      cells.splice(i + 1, 0, { kind: "code", title: "", code: lines.slice(line).join("\n").replace(/^\s*\n/, ""), description: "" });
    }
    markDirty();
    renderCells();
  }

  renderCells();
  $("#add-cell").onclick = () => { sync(); cells.push({ kind: "code", title: "", code: "", description: "" }); markDirty(); renderCells(); };
  $("#show-src").onclick = () => { $("#src").hidden = !$("#src").hidden; };
  $("#save-cells").onclick = async () => {
    sync();
    try {
      const r = await api(`/api/references/${ref.id}/cells`, { method: "PUT", json: cells });
      cells = r.shown_version.cells.map(c => ({ ...c }));
      dirty = false; $("#dirty").textContent = "";
      renderCells();
      const orphans = r.test_list.filter(t => t.orphan).length;
      toast(`сохранено: ${cells.length} блоков` + (orphans ? ` · ${orphans} тест(ов) без блока` : ""));
    } catch (e) { toast(e.message, true); }
  };
  const resplit = async (mode, btn) => {
    if (dirty && !confirm("Несохранённые правки пропадут. Продолжить?")) return;
    btn.disabled = true; const old = btn.textContent; btn.textContent = "думаю…";
    try {
      cells = await api(`/api/references/${ref.id}/resplit`, { method: "POST", json: { mode } });
      renderCells(); markDirty();
      toast(`предложено ${cells.length} блоков — проверьте и сохраните`);
    } catch (e) { toast(e.message, true); }
    btn.disabled = false; btn.textContent = old;
  };
  $("#split-ast").onclick = e => resplit("ast", e.target);
  $("#split-llm").onclick = e => resplit("llm", e.target);
}

async function tabTests(ref, box) {
  const blocks = ref.shown_version.cells.map(c => c.title);
  const orphans = ref.test_list.filter(t => t.orphan);
  box.innerHTML = `
    ${orphans.length ? `<fieldset class="box warnbox"><legend class="warn">БЕЗ БЛОКА: ${orphans.length}</legend>
      <p class="muted">Блок, к которому были привязаны эти тесты, пропал или переименован в новой версии. Выберите новый блок.</p>
      ${orphans.map(t => `<div class="row"><span class="warn">⚠</span> ${esc(t.name || "тест #" + t.id)}
        <span class="muted">был: «${esc(t.block)}»</span> →
        <select data-bind="${t.id}"><option value="">— выбрать блок —</option>${blocks.map(b => `<option>${esc(b)}</option>`).join("")}<option value="__all">весь код</option></select>
      </div>`).join("")}
    </fieldset>` : ""}
    <fieldset class="box"><legend>ТЕСТЫ: ${ref.test_list.length}</legend>
      <p class="muted">Тест — Python-код, который выполняется после ячеек. Значение последнего выражения — результат.
      «= эталон»: результат должен совпасть с результатом на эталоне (например <code>quicksort([3,1,2])</code>,
      <code>tuple(model(torch.randn(8,3,32,32)).shape)</code>, <code>sum(p.numel() for p in model.parameters())</code>).
      «assert»: результат должен быть True (например <code>losses[-1] &lt; losses[0]</code>).
      При проверке тесты идут на эталоне и на вашем коде в разных ядрах. Тест, который падает на самом эталоне, помечается сломанным и не учитывается.
      Предложенные LLM тесты не участвуют в проверке, пока вы их не подтвердите.</p>
      <div class="row" style="margin-bottom:10px">
        <button id="t-run">прогнать на эталоне</button>
        <button id="t-suggest">предложить через LLM</button>
        <span id="t-status" class="muted"></span>
      </div>
      <div id="tlist"></div>
      <button id="t-add" class="mt">+ тест</button>
    </fieldset>`;

  $$("[data-bind]", box).forEach(sel => sel.onchange = async () => {
    if (!sel.value) return;
    await api(`/api/tests/${sel.dataset.bind}`, { method: "PATCH", json: { block: sel.value === "__all" ? "" : sel.value } });
    toast("привязан"); viewRef(ref.id, "tests");
  });

  const list = $("#tlist");
  const render = (t) => {
    const el = document.createElement("div");
    el.className = "cell";
    el.innerHTML = `<div class="head">
        <input class="title" data-f="name" value="${esc(t.name)}" placeholder="название теста">
        <select data-f="block"><option value="">весь код</option>${blocks.map(b => `<option ${b === t.block ? "selected" : ""}>${esc(b)}</option>`).join("")}
          ${t.orphan ? `<option selected value="${esc(t.block)}">⚠ ${esc(t.block)} (нет блока)</option>` : ""}</select>
        <select data-f="mode"><option value="match" ${t.mode === "match" ? "selected" : ""}>= эталон</option><option value="assert" ${t.mode === "assert" ? "selected" : ""}>assert</option></select>
        ${t.approved ? "" : '<span class="warn">предложен LLM</span> <button class="small" data-a="approve">подтвердить</button>'}
        <button class="small" data-a="save">сохранить</button>
        <button class="small danger" data-a="del">x</button>
      </div>
      <div class="tres">${t.broken ? `<span class="err">✗ СЛОМАН:</span> <span class="muted">${esc(t.broken)}</span>` : ""}</div>`;
    el.dataset.tid = t.id ?? "";
    list.appendChild(el);
    const cm = editor(el, t.code);
    $("[data-a=save]", el).onclick = async () => {
      const body = { code: cm.getValue() };
      $$("[data-f]", el).forEach(f => body[f.dataset.f] = f.value);
      try {
        const saved = t.id ? await api(`/api/tests/${t.id}`, { method: "PATCH", json: body })
                           : await api(`/api/references/${ref.id}/tests`, { method: "POST", json: body });
        Object.assign(t, saved); toast("тест сохранён");
      } catch (e) { toast(e.message, true); }
    };
    $("[data-a=del]", el).onclick = async () => {
      if (t.id && !confirm("Удалить тест?")) return;
      if (t.id) await api(`/api/tests/${t.id}`, { method: "DELETE" });
      el.remove();
    };
    const ap = $("[data-a=approve]", el);
    if (ap) ap.onclick = async () => { await api(`/api/tests/${t.id}`, { method: "PATCH", json: { approved: true } }); ap.remove(); };
  };
  ref.test_list.forEach(render);
  $("#t-run").onclick = async e => {
    e.target.disabled = true;
    $("#t-status").innerHTML = '<span class="cursor">запускаю эталон в отдельном ядре</span>';
    try {
      const res = await api(`/api/references/${ref.id}/tests/run`, { method: "POST" });
      res.forEach(r => {
        const el = $(`[data-tid="${r.id}"] .tres`, list);
        if (el) el.innerHTML = r.broken ? `<span class="err">✗ СЛОМАН:</span> <span class="muted">${esc(r.broken)}</span>`
                                        : `<span class="ok">✓ эталон →</span> <code>${esc(r.value)}</code>`;
      });
      const broken = res.filter(r => r.broken).length;
      $("#t-status").innerHTML = broken ? `<span class="err">сломано: ${broken} из ${res.length}</span>` : `<span class="ok">все ${res.length} работают на эталоне</span>`;
    } catch (err) { $("#t-status").innerHTML = `<span class="err">${esc(err.message)}</span>`; }
    e.target.disabled = false;
  };
  $("#t-suggest").onclick = async e => {
    e.target.disabled = true;
    $("#t-status").innerHTML = '<span class="cursor">LLM придумывает тесты</span>';
    try {
      await api(`/api/references/${ref.id}/tests/suggest`, { method: "POST" });
      toast("тесты предложены — проверьте и подтвердите"); viewRef(ref.id, "tests");
    } catch (err) { $("#t-status").innerHTML = `<span class="err">${esc(err.message)}</span>`; e.target.disabled = false; }
  };
  $("#t-add").onclick = () => render({ id: null, name: "", block: blocks[0] || "", code: "", mode: "match", approved: true });
}

async function tabVersions(ref, box, shown) {
  const vs = [...ref.versions].reverse();
  box.innerHTML = `<fieldset class="box"><legend>ВЕРСИИ: ${vs.length}</legend>
    <table><thead><tr><th>версия</th><th>загружена</th><th>блоков</th><th></th></tr></thead><tbody>
    ${vs.map(v => `<tr><td>v${v.number}${v.number === ref.version ? ' <span class="ok">текущая</span>' : ""}</td>
      <td>${fmtDate(v.created_at)}</td><td>${v.blocks}</td>
      <td><button class="small" data-show="${v.number}">код</button>
      ${v.number > 1 ? `<button class="small" data-diff="${v.number}">diff с v${v.number - 1}</button>` : ""}</td></tr>`).join("")}
    </tbody></table><div id="vout" class="mt"></div></fieldset>`;
  $$("[data-diff]", box).forEach(b => b.onclick = async () => {
    const n = +b.dataset.diff;
    const { diff } = await api(`/api/references/${ref.id}/diff?a=${n - 1}&b=${n}`);
    $("#vout").innerHTML = `<h3>v${n - 1} → v${n}</h3><pre class="src diff">${diffHtml(diff)}</pre>`;
  });
  $$("[data-show]", box).forEach(b => b.onclick = async () => {
    const r = await api(`/api/references/${ref.id}?version=${b.dataset.show}`);
    const out = $("#vout");
    out.innerHTML = `<h3>v${b.dataset.show}</h3>` + r.shown_version.cells.map((c, i) =>
      `<div class="cell"><div class="head"><span class="num">[${String(i + 1).padStart(2, "0")}]</span> ${esc(c.title)} <span class="muted">${c.kind}</span></div><div class="code" data-i="${i}"></div></div>`).join("");
    $$(".code", out).forEach(el => editor(el, r.shown_version.cells[+el.dataset.i].code, { readOnly: true }));
  });
}

const bar = (frac, width = 12) => {
  const n = Math.max(0, Math.min(width, Math.round(frac * width)));
  return "█".repeat(n) + `<span class="faint">${"░".repeat(width - n)}</span>`;
};
const GRADE_CLS = { "забыл": "err", "трудно": "warn", "нормально": "ok", "легко": "ok" };

async function tabAttempts(ref, box) {
  const list = await api(`/api/references/${ref.id}/attempts`);
  const st = { active: ["warn", "в процессе"], checking: ["warn", "проверяется"], submitted: ["ok", "сдано"], abandoned: ["muted", "брошено"] };
  const done = list.filter(a => a.status === "submitted");
  const maxMs = Math.max(1, ...done.map(a => a.total_ms));
  box.innerHTML = `<fieldset class="box"><legend>ПОПЫТКИ: ${list.length}</legend>
    <p class="muted">следующее повторение: ${ref.due_at ? `<b class="ok">${ref.due_at.slice(0, 10)}</b>` : "ещё не назначено"}</p>
    ${list.length ? `<div class="scroll-x"><table class="stack"><thead><tr><th>дата</th><th>режим</th><th>статус</th><th>оценка</th><th>время</th><th>уровень</th><th>подсказки</th></tr></thead><tbody>
    ${list.map(a => `<tr class="link" data-id="${a.id}"><td data-label="дата" class="nowrap stack-title">${fmtDate(a.started_at)}</td><td data-label="режим">${a.mode_name}</td>
      <td data-label="статус" class="${st[a.status][0]}">${st[a.status][1]}</td>
      <td data-label="оценка" class="nowrap">${a.score != null ? `${bar(a.score / 100)} ${String(a.score).padStart(3, "\u00a0")}` : "—"}</td>
      <td data-label="время" class="nowrap">${a.status === "submitted" ? `${bar(a.total_ms / maxMs, 8)} ${fmtMs(a.total_ms)}` : fmtMs(a.total_ms)}</td>
      <td data-label="уровень" class="${GRADE_CLS[a.grade] || "muted"}">${a.grade ?? "—"}${a.grade_manual ? ' <span class="muted" title="поставлен вручную">✎</span>' : ""}${a.conflicts ? ' <span class="warn" title="конфликт тестов и судьи">⚠</span>' : ""}</td>
      <td data-label="подсказки" class="${a.hints ? "warn" : "muted"}">${a.hints}</td></tr>`).join("")}
    </tbody></table></div>` : '<p class="muted">попыток ещё не было</p>'}
    ${done.length ? '<div id="progress" class="mt"></div>' : ""}</fieldset>`;
  if (done.length) progressCharts($("#progress", box), list);
  $$("tr[data-id]", box).forEach(tr => tr.onclick = () => { location.hash = `#/attempt/${tr.dataset.id}`; });
}

// ---------------- НОУТБУК (попытка) ----------------
async function viewAttempt(id) {
  let a = await api(`/api/attempts/${id}`);
  const task = () => a.task;
  const readOnly = a.status !== "active";
  const blockOf = i => task().blocks.find(b => b.index === i);
  let cells = a.cells.map(c => ({ ...c, outputs: [], count: null }));
  let editors = [], sel = Math.max(0, cells.findIndex(c => !c.given));
  const kc = new KernelClient(a.kernel_key);
  const loadedAt = Date.now(), baseMs = a.total_ms;
  const totalMs = () => readOnly ? a.total_ms : baseMs + (Date.now() - loadedAt);
  let focusIdx = null, focusAt = 0;  // таймер ячейки идёт, пока её редактор в фокусе
  let running = 0;

  view.innerHTML = `
    <p><a href="#/ref/${a.reference_id}/attempts">&lt; к эталону</a></p>
    <div class="nbbar">
      <h2>${esc(task().title)}</h2>
      <span class="muted">${esc(a.mode_name)}</span>
      <span class="grow"></span>
      <span>ВСЕГО <b id="total" class="timer">${fmtMs(totalMs())}</b></span>
    </div>
    ${readOnly ? `<div class="row nbtools"><span class="${a.status === "abandoned" ? "muted" : "ok"}">${{ checking: "СДАНО · ПРОВЕРЯЕТСЯ", submitted: "СДАНО", abandoned: "БРОШЕНО" }[a.status]}</span></div>`
      : `<div class="nb-sticky"><div id="tb"></div><div class="row tb2"><span id="fresh" class="warn small"></span><span class="grow"></span>
           <button id="abandon" class="danger">бросить</button><button id="submit" class="primary">сдать</button></div></div>`}
    <div id="report"></div>
    <fieldset class="box"><legend>ЗАДАНИЕ</legend><div id="task"></div></fieldset>
    <div id="plan"></div>
    <div id="cells"></div>
    ${readOnly ? "" : '<p class="muted small">Shift+Enter — запустить и перейти · Ctrl/Cmd+Enter — запустить · панель сверху действует на выбранную ячейку</p>'}`;

  function renderTask() {
    const t = task();
    const hints = t.hints;
    let html = "";
    if (a.mode === "scratch") {
      html += t.task ? `<div class="md"></div>` : `<p class="muted">Напишите «${esc(t.title)}» с нуля. (Описание задачи не задано — его можно сгенерировать кнопкой «описания через LLM» на экране эталона.)</p>`;
      if (t.tag) html += `<p class="muted">тема: ${esc(t.tag)}</p>`;
      html += hints.plan ? `<p class="warn">ПОДСКАЗКА · план:</p><pre class="hint">${esc(hints.plan)}</pre>`
                         : (readOnly ? "" : '<button id="hint-plan" class="small warn-btn">подсказка: план блоков</button>');
    } else if (a.mode === "block") {
      const tb = blockOf(t.target);
      html += `<p>Повторите блок <b>«${esc(t.target_title)}»</b>. Предыдущие блоки эталона даны и выполняются сами, чтобы были нужные переменные.</p>`;
      if (tb && tb.description) html += `<div class="md"></div>`;
    } else {
      html += t.task ? `<div class="md"></div>` : `<p>Напишите «${esc(t.title)}» по описаниям блоков ниже.</p>`;
      if (a.mode === "gaps") html += '<p class="muted">Часть блоков дана (помечены ДАНО) — их можно запускать. Остальные восстановите.</p>';
    }
    $("#task").innerHTML = html;
    const mdEl = $("#task .md");
    if (mdEl) mdInto(mdEl, a.mode === "block" ? blockOf(t.target).description : t.task);
    const hp = $("#hint-plan");
    if (hp) hp.onclick = () => useHint("plan");
  }

  function cellHead(c) {
    const b = c.block != null ? blockOf(c.block) : null;
    const hintKey = c.block != null ? String(c.block) : null;
    const canHint = !readOnly && b && !b.given && !task().hints[hintKey];
    let label = "";
    if (b) label = b.given ? `<span class="ok">ДАНО</span> · ${esc(b.title)}` : `<span class="muted">блок ${b.index + 1}:</span> `
      + (b.description ? "" : `<span class="muted">${esc(b.title)} (${b.kind}) — описания нет</span>`);
    return `<div class="cellhead">
      <span class="prompt" data-count>[${c.count ?? " "}]</span>
      <span class="grow blocklabel">${label}${b && !b.given && b.description ? '<div class="md desc-md small"></div>' : ""}</span>
      <span class="muted timer small" data-ctime>${fmtMs(c.time_ms)}</span>
      ${readOnly ? "" : `<button class="small" data-a="run" title="запустить (Shift+Enter)">▶</button>
        ${canHint ? '<button class="small warn-btn" data-a="hint">подсказка</button>' : ""}
        ${b && b.given ? "" : '<button class="small danger" data-a="del" title="удалить ячейку">✕</button>'}`}
    </div>
    ${hintKey && task().hints[hintKey] ? `<pre class="hint"><span class="warn">ПОДСКАЗКА:</span>\n${esc(task().hints[hintKey])}</pre>` : ""}`;
  }

  function paintOutputs(i) {
    const c = cells[i];
    if (!c.el || c.md) return;
    $("[data-count]", c.el).textContent = c.running ? "[*]" : `[${c.count ?? " "}]`;
    renderOutputs($(".outs", c.el), c.outputs, { refId: a.reference_id });
  }

  function renderCells() {
    stopCellTimer();
    const list = $("#cells");
    list.innerHTML = "";
    editors = cells.map((c, i) => {
      const el = document.createElement("div");
      const b = c.block != null ? blockOf(c.block) : null;
      c.el = el;
      el.onclick = () => select(i);
      if (c.md) {  // текст из эталона: отрисованный markdown, не редактируется и не выполняется
        el.className = "nbcell is-md";
        el.innerHTML = '<div class="md"></div>';
        mdInto($(".md", el), c.code);
        list.appendChild(el);
        return null;
      }
      el.className = "nbcell" + (b && b.given ? " given" : "");
      el.innerHTML = cellHead(c) + '<div class="ed"></div><div class="outs"></div>';
      list.appendChild(el);
      if (b && !b.given && b.description) mdInto($(".desc-md", el), b.description);
      const cm = editor($(".ed", el), c.code, {
        readOnly: readOnly || (b && b.given) ? "nocursor" : false,
        extraKeys: {
          "Shift-Enter": () => runCell(i, true), "Ctrl-Enter": () => runCell(i), "Cmd-Enter": () => runCell(i),
          Tab: cm2 => cm2.somethingSelected() ? cm2.execCommand("indentMore") : cm2.replaceSelection("    "),
          "Shift-Tab": cm2 => cm2.execCommand("indentLess"),
        },
      });
      cm.on("change", () => { c.code = cm.getValue(); });
      cm.on("focus", () => { select(i); startCellTimer(i); });
      cm.on("blur", stopCellTimer);
      $$("[data-a]", el).forEach(btn => btn.onclick = e => { e.stopPropagation(); cellAction(btn.dataset.a, i); });
      paintOutputs(i);
      return cm;
    });
    select(Math.min(sel, cells.length - 1));
  }

  function select(i) { sel = i; cells.forEach((c, k) => c.el && c.el.classList.toggle("sel", k === i)); }
  function startCellTimer(i) { stopCellTimer(); if (!readOnly) { focusIdx = i; focusAt = Date.now(); } }
  function stopCellTimer() {
    if (focusIdx != null && cells[focusIdx]) cells[focusIdx].time_ms += Date.now() - focusAt;
    focusIdx = null;
  }
  const liveCellMs = i => cells[i].time_ms + (focusIdx === i ? Date.now() - focusAt : 0);
  const newCell = () => ({ block: null, given: false, code: "", time_ms: 0, outputs: [], count: null });

  function cellAction(act, i) {
    stopCellTimer();
    if (act === "run") return runCell(i);
    if (act === "hint") return useHint(String(cells[i].block));
    if (act === "up" && i > 0) { [cells[i - 1], cells[i]] = [cells[i], cells[i - 1]]; sel = i - 1; }
    if (act === "down" && i < cells.length - 1) { [cells[i + 1], cells[i]] = [cells[i], cells[i + 1]]; sel = i + 1; }
    if (act === "add") { cells.splice(i + 1, 0, newCell()); sel = i + 1; }
    if (act === "del") {
      if (cells[i].code.trim() && !confirm("Удалить ячейку?")) return;
      cells.splice(i, 1);
      sel = Math.max(0, i - 1);
    }
    renderCells();
    if (act === "add" && editors[sel]) editors[sel].focus();
  }

  async function runCell(i, advance = false) {
    const c = cells[i];
    if (!c || c.md) {
      if (advance) focusNext(i);
      return true;
    }
    if (editors[i]) c.code = editors[i].getValue();
    if (advance) focusNext(i);  // как в Jupyter: фокус уходит дальше сразу, не дожидаясь выполнения
    c.running = true; c.outputs = []; paintOutputs(i);
    running++; bar.setKernel("busy");
    const fr = $("#fresh"); if (fr) fr.textContent = "";
    try {
      // у данных блоков эталона передаём название: сервер запомнит время и сохранит кэш тяжёлого
      const b = c.given && c.block != null ? blockOf(c.block) : null;
      const r = await kc.run(c.code, outs => { c.outputs = outs; paintOutputs(i); }, b ? { block: b.title } : {});
      c.outputs = r.outputs; c.count = r.count;
    } catch (e) {
      c.outputs = [{ type: "error", ename: "Ошибка сервера", evalue: e.message }];
    }
    c.running = false; running--;
    if (!running) kc.state().then(s => bar.setKernel(s)).catch(() => {});
    paintOutputs(i);
    return c.outputs.every(o => o.type !== "error");
  }
  function focusNext(i) {
    let j = cells.findIndex((x, k) => k > i && !x.md);
    if (j < 0) { stopCellTimer(); cells.push(newCell()); renderCells(); j = cells.length - 1; }
    select(j);
    if (editors[j]) { editors[j].focus(); cells[j].el.scrollIntoView({ block: "nearest" }); }
  }

  async function useHint(key) {
    if (!confirm("Подсказка будет отмечена как использованная и снизит оценку.\nОткрыть?")) return;
    stopCellTimer();
    try {
      a = await api(`/api/attempts/${id}/hint`, { method: "POST", json: { key } });
      renderTask(); renderCells();
    } catch (e) { toast(e.message, true); }
  }

  const draft = () => ({ cells: cells.map(c => ({ block: c.block, given: c.given, md: !!c.md, code: c.code, time_ms: Math.round(c.time_ms) })),
                         total_ms: Math.round(totalMs()) });
  const saveDraft = (closing = false) => {
    if (readOnly) return;
    stopCellTimer();
    return fetch(`/api/attempts/${id}/draft${closing ? "?close=true" : ""}`, { method: "PUT", keepalive: closing, headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft()) }).catch(() => {});
  };

  let bar = { setKernel() {} };
  if (!readOnly) {
    bar = toolbar($("#tb"), [TB.add, TB.up, TB.down, "|", TB.run, TB.runAll, "|", TB.clear, TB.stop, TB.restart], {
      add: () => cellAction("add", sel), up: () => cellAction("up", sel), down: () => cellAction("down", sel),
      run: () => runCell(sel, true),
      runAll: async () => { for (let i = 0; i < cells.length; i++) if (!(await runCell(i))) break; },
      clear: () => { cells.forEach((c, i) => { c.outputs = []; c.count = null; paintOutputs(i); }); },
      stop: () => kc.interrupt(),
      restart: async () => {
        if (!confirm("Перезапустить ядро? Все переменные пропадут.")) return;
        bar.setKernel("restarting");
        await kc.restart();
        cells.forEach((c, i) => { c.count = null; paintOutputs(i); });
        bar.setKernel("idle");
      },
    });
    bar.setKernel(a.kernel);
  }

  renderTask();
  renderCells();
  if (readOnly) {
    if (a.status !== "abandoned") showReport(a);
    return;
  }

  // ждём ядро; в «повторить блок» — сами выполняем данные блоки до целевого
  let alive = true;  // false после сдачи / ухода со страницы
  (async function waitKernel() {
    let s = a.kernel;
    while (alive && !["idle", "busy"].includes(s)) {
      await new Promise(r => setTimeout(r, 1000));
      s = await kc.state().catch(() => "?");
      if (s === "off") s = await kc.start().catch(() => "off");
      if (!running) bar.setKernel(s);
    }
    if (!alive) return;
    if (task().auto_run) {
      showPlan();
    } else if (cells.some(c => c.code.trim() && !c.given)) {
      $("#fresh").textContent = "ядро новое: переменные сброшены — «все», чтобы восстановить";
    }
  })();

  // План автозапуска для «повторить блок»: что выполнится, что возьмётся из кэша, что пропустится
  async function showPlan() {
    const box = $("#plan");
    let plan;
    try { plan = await api(`/api/attempts/${id}/autorun`); } catch (e) { box.innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    if (!plan.items.length) return;
    const act = { run: "выполнить", cache: "загрузить кэш", skip: "пропустить" };
    const est = it => it.action === "cache" ? `кэш ${fmtSize(it.cache.size)}` : it.est_ms != null ? `≈ ${it.est_ms < 1000 ? "<1 с" : fmtMs(it.est_ms)}` : "время неизвестно";
    const total = () => {
      const run = plan.items.filter(it => it.action === "run" || (it.action === "skip" && it.force));
      const known = run.reduce((t, it) => t + (it.est_ms || 0), 0);
      const unknown = run.filter(it => it.est_ms == null).length;
      return `≈ ${fmtMs(known)}${unknown ? ` + ${unknown} блок(ов) без истории запусков` : ""}`;
    };
    box.innerHTML = `<fieldset class="box"><legend>ПЕРЕД ПОВТОРОМ</legend>
      <p class="small muted">Эти блоки эталона нужны, чтобы появились переменные. Тяжёлые не пересчитываются, если есть кэш.</p>
      <table class="plan"><tbody>${plan.items.map((it, k) => `<tr>
        <td>${esc(it.title)}${it.heavy ? ' <span class="warn small">тяжёлый</span>' : ""}</td>
        <td class="${it.action === "skip" ? "warn" : it.action === "cache" ? "ok" : ""}">${act[it.action]}${it.reason ? ` <span class="muted small">— ${esc(it.reason)}</span>` : ""}
          ${it.action === "skip" ? `<label class="small"><input type="checkbox" data-force="${k}"> выполнить всё равно</label>` : ""}</td>
        <td class="muted small nowrap">${est(it)}</td></tr>`).join("")}</tbody></table>
      <div class="row mt"><button class="primary" id="plan-go">запустить</button><span class="muted small" id="plan-total">итого ${total()}</span></div>
    </fieldset>`;
    $$("[data-force]", box).forEach(cb => cb.onchange = () => { plan.items[+cb.dataset.force].force = cb.checked; $("#plan-total").textContent = "итого " + total(); });
    $("#plan-go").onclick = async () => {
      $("#plan-go").disabled = true;
      const byBlock = idx => cells.findIndex(c => c.block === idx);
      for (const it of plan.items) {
        if (!alive) return;
        const i = byBlock(it.index);
        if (i < 0) continue;
        const c = cells[i];
        if (it.action === "cache") {
          c.running = true; c.outputs = []; paintOutputs(i);
          try {
            const r = await kc.run("", outs => { c.outputs = outs; paintOutputs(i); }, { block: it.title, cache_load: true });
            c.outputs = r.outputs; c.count = r.count;
          } catch (e) { c.outputs = [{ type: "error", ename: "Кэш", evalue: e.message }]; }
          c.running = false; paintOutputs(i);
          if (c.outputs.some(o => o.type === "error")) { toast("кэш не загрузился — дальше могут упасть блоки", true); break; }
        } else if (it.action === "skip" && !it.force) {
          c.outputs = [{ type: "stream", name: "stderr", text: "пропущен при автозапуске: тяжёлый блок без кэша\n" }]; paintOutputs(i);
        } else if (!(await runCell(i))) { toast("предыдущий блок упал — проверьте данные и окружение", true); break; }
      }
      box.innerHTML = "";
      kc.state().then(s2 => bar.setKernel(s2)).catch(() => {});
    };
  }

  // таймеры, автосохранение
  const tick = setInterval(() => {
    if (!document.body.contains($("#total"))) return clearInterval(tick);
    $("#total").textContent = fmtMs(totalMs());
    if (focusIdx != null && cells[focusIdx]?.el) { const t = $("[data-ctime]", cells[focusIdx].el); if (t) t.textContent = fmtMs(liveCellMs(focusIdx)); }
  }, 500);
  const autosave = setInterval(() => {
    if (!document.body.contains($("#total"))) return clearInterval(autosave);
    const f = focusIdx; saveDraft(); if (f != null) startCellTimer(f);
  }, 15000);
  const onUnload = () => saveDraft(true);
  window.addEventListener("beforeunload", onUnload);
  const teardown = () => { alive = false; kc.alive = false; leaveHook = null; window.removeEventListener("beforeunload", onUnload); clearInterval(tick); clearInterval(autosave); };
  leaveHook = () => { teardown(); saveDraft(true); };

  $("#abandon").onclick = async () => {
    if (!confirm("Бросить попытку? Она сохранится в истории как брошенная.")) return;
    teardown();
    await saveDraft();
    await api(`/api/attempts/${id}/abandon`, { method: "POST" });
    location.hash = `#/ref/${a.reference_id}/attempts`;
  };
  $("#submit").onclick = async () => {
    if (!confirm("Сдать работу?")) return;
    stopCellTimer();
    teardown();
    try {
      await api(`/api/attempts/${id}/submit`, { method: "POST", json: draft() });
      await viewAttempt(id);
      window.scrollTo(0, 0);
    } catch (e) { toast(e.message, true); }
  };
}

// ---------------- РЕЗУЛЬТАТ ПРОВЕРКИ ----------------
const VERDICT_CLS = { "верно": "ok", "частично": "warn", "неверно": "err" };
const TEST_ST = { pass: ["ok", "✓ прошёл"], fail: ["err", "✗ не совпал"], error: ["err", "✗ ошибка"], broken: ["warn", "⚠ сломан на эталоне"] };

async function showReport(a) {
  const box = $("#report");
  if (!box) return;
  // пока идёт проверка — опрашиваем сервер; как только готовы тесты, показываем блоки,
  // а вердикты судьи дописываются по мере готовности
  let shown = "";
  while (a.status === "checking") {
    const rep = a.report || {};
    const sig = JSON.stringify(rep);
    if (sig !== shown) {
      shown = sig;
      box.innerHTML = `<fieldset class="box"><legend>ПРОВЕРКА ИДЁТ</legend>
          <p class="cursor">${esc(rep.progress || "в очереди")}</p>
          ${rep.partial ? `<p class="muted small">Выполнение и тесты готовы — смотрите блоки ниже. Оценка появится, когда судья закончит.</p>` : ""}
        </fieldset>
        ${rep.partial ? rep.blocks.map(reportBlock).join("") + commonTests(rep) : ""}`;
      bindCompare(box, rep);
    }
    await new Promise(r => setTimeout(r, 1500));
    if (!document.body.contains(box)) return;
    a = await api(`/api/attempts/${a.id}`);
  }
  const bar = $(".nbtools span");
  if (bar) bar.textContent = "СДАНО";
  const rep = a.report;
  if (!rep || rep.fatal) {
    box.innerHTML = `<fieldset class="box"><legend>ПРОВЕРКА</legend>
      <p class="err">${esc(rep?.fatal || "отчёта нет")}</p><button id="recheck">перепроверить</button></fieldset>`;
  } else {
    const j = rep.judge, w = rep.weights;
    const scoreCls = rep.score >= 80 ? "ok" : rep.score >= 50 ? "warn" : "err";
    const prev = rep.prev_attempt;
    box.innerHTML = `
      <fieldset class="box"><legend>ОТЧЁТ</legend>
        <div class="row">
          <span class="bigscore ${scoreCls}">${rep.score}</span><span class="muted">/ 100</span>
          <span class="gradebig ${GRADE_CLS[a.grade_name]}">${(a.grade_name || "").toUpperCase()}</span>
          ${a.grade_manual ? '<span class="muted">(вручную)</span>' : ""}
          <span class="grow"></span>
          <span>время <b>${fmtMs(a.total_ms)}</b>${prev ? ` <span class="muted">· прошлый раз ${fmtMs(prev.total_ms)}, оценка ${prev.score}</span>` : ""}</span>
        </div>
        <div class="mt">уровень: ${(rep.grade_reasons || []).map(esc).join(" · ")}</div>
        <div>следующее повторение: <b>${a.due_at || "—"}</b></div>
        <div class="row mt">
          <span class="muted">не согласен с оценкой →</span>
          ${Object.entries(a.grades).map(([g, n]) => `<button class="small ${+g === a.grade ? "sel" : ""}" data-grade="${g}">${n}</button>`).join("")}
          ${a.grade_manual ? '<button class="small raw" data-grade="">вернуть автоматический</button>' : ""}
        </div>
        ${rep.conflicts ? `<p class="warn mt">⚠ конфликтов тестов и судьи: ${rep.conflicts} — оценка блока ниже посчитана по формуле, но решите сами, кто прав, и при необходимости поправьте уровень</p>` : ""}
        <ul class="warnings">${(rep.warnings || []).map(x => `<li class="${x.level}">${esc(x.text)}</li>`).join("")}</ul>
        <details class="mt"><summary>как посчитана оценка</summary>
          <pre class="formula">блок = (${w.w_exec}·выполнение + ${w.w_tests}·тесты + ${w.w_judge}·судья) / (сумма весов доступных слоёв)
  выполнение: 1 — без ошибок, 0 — падает
  тесты: доля прошедших (сломанные на эталоне не считаются)
  судья: верно 1 · частично 0.5 · неверно 0
  слой недоступен (нет тестов / судья молчит) → его вес не входит в сумму
подсказка: −${w.hint_penalty}% оценки блока · план в режиме «с нуля»: −${w.plan_penalty}% общей
пустой блок = 0
итог = среднее по блокам, которые вы писали (+ тесты на весь код как ещё один блок)
уровень: ≥90 легко · ≥70 нормально · ≥50 трудно · иначе забыл
  подсказки: −1 уровень · время дольше прошлого раза (тот же режим) более чем на ${w.slower_pct}%: −1 уровень
веса меняются в настройках</pre>
        </details>
        <p class="muted mt">судья: <b>${esc(j.provider)} · ${esc(j.model)}</b>
          ${j.used ? '<span class="ok">ответил</span>' : '<span class="warn">судья недоступен</span>'}
          ${j.error ? `<span class="warn">— ${esc(j.error)}</span>` : ""}
          · основа: ${esc(rep.basis)} · <button class="small" id="recheck">перепроверить</button></p>
        ${rep.reference_ok ? "" : `<p class="warn">⚠ эталон сам не выполняется: ${esc(rep.reference_error)}</p>`}
        ${rep.broken_tests.length ? `<p class="warn">⚠ сломанных тестов: ${rep.broken_tests.length} — не учитывались (<a href="#/ref/${a.reference_id}/tests">поправить</a>)</p>` : ""}
      </fieldset>
      ${rep.blocks.map(reportBlock).join("")}
      ${commonTests(rep)}`;
    bindCompare(box, rep);
    $$("[data-grade]", box).forEach(btn => btn.onclick = async () => {
      const g = btn.dataset.grade ? +btn.dataset.grade : null;
      try {
        a = await api(`/api/attempts/${a.id}/grade`, { method: "POST", json: { grade: g } });
        toast(`уровень: ${a.grade_name} · повторение ${a.due_at}`);
        showReport(a);
      } catch (e) { toast(e.message, true); }
    });
  }
  const rc = $("#recheck");
  if (rc) rc.onclick = async () => {
    a = await api(`/api/attempts/${a.id}/recheck`, { method: "POST" });
    showReport(a);
  };
}

// side-by-side рисуем при первом раскрытии (CodeMirror в скрытом блоке считает размеры неверно)
function bindCompare(box, rep) {
  $$("details.cmp", box).forEach(d => {
    const draw = () => {
      if (!d.open || d.dataset.ready) return;
      d.dataset.ready = 1;
      const b = rep.blocks[+d.dataset.i];
      editor($(".mine", d), b.user_code || "# (пусто)", { readOnly: true });
      editor($(".theirs", d), b.ref_code, { readOnly: true });
    };
    d.addEventListener("toggle", draw);
    draw();  // блоки с конфликтом раскрыты сразу
  });
}

const pct = v => (v == null ? '<span class="muted">—</span>' : Math.round(v * 100));

function reportBlock(b, i) {
  const j = b.judge;
  let status;
  if (b.given) status = '<span class="muted">ДАНО</span>';
  else if (!b.user_code.trim()) status = '<span class="err">ПУСТО</span>';
  else if (b.pending) status = '<span class="muted cursor">судья смотрит</span>';
  else if (j && j.available) status = `<span class="${VERDICT_CLS[j.verdict]}">${j.verdict.toUpperCase()}</span>`;
  else status = b.score >= 80 ? '<span class="ok">OK</span>' : b.score >= 50 ? '<span class="warn">ЧАСТИЧНО</span>' : '<span class="err">ОШИБКИ</span>';
  const list = (arr, cls) => arr.map(x => `<li class="${cls}">${esc(x)}</li>`).join("");
  const p = b.parts;
  const time = b.time_ms != null && !b.given && b.index != null
    ? `<span class="muted">время</span> ${fmtMs(b.time_ms)}${b.prev_time_ms != null ? ` <span class="${b.time_ms > b.prev_time_ms ? "warn" : "ok"}">(прошлый раз ${fmtMs(b.prev_time_ms)})</span>` : ""}` : "";
  return `<fieldset class="box ${b.conflict ? "warnbox" : ""}"><legend>${b.index != null ? String(b.index + 1).padStart(2, "0") + " · " : ""}${esc(b.title)}</legend>
    <div class="row">${status}
      ${b.conflict ? '<span class="warn">⚠ КОНФЛИКТ</span>' : ""}
      ${b.score != null ? `<span class="muted">оценка блока:</span> ${b.score}` : ""}
      ${b.hint ? '<span class="warn">подсказка использована</span>' : ""}
      <span class="grow"></span>${time}
      ${b.given ? "" : b.exec_ok ? '<span class="ok">выполняется</span>' : `<span class="err">${b.user_code.trim() ? "ошибка выполнения" : "не написан"}</span>`}
    </div>
    ${b.conflict ? `<p class="warn">${esc(b.conflict)}. Посмотрите код рядом с эталоном и решите сами — уровень можно поправить кнопками выше.</p>` : ""}
    ${p ? `<div class="muted small">слои: выполнение ${pct(p.exec)} · тесты ${pct(p.tests)}${p.tests_n ? ` (${p.tests_n})` : ""} · судья ${pct(p.judge)}</div>` : ""}
    ${b.exec_errors.length ? `<ul>${list(b.exec_errors, "err")}</ul>` : ""}
    ${b.tests.map(testResult).join("")}
    ${j && j.available ? `
      ${j.errors.length ? `<div class="mt">ошибки:<ul>${list(j.errors, "err")}</ul></div>` : ""}
      ${j.logic_differences.length ? `<div>отличия в логике (не ошибки):<ul>${list(j.logic_differences, "muted")}</ul></div>` : ""}
      ${j.comment && !j.exact ? `<p class="muted">судья: ${esc(j.comment)}</p>` : ""}
      ${j.adjusted ? `<p class="warn small">⚙ ${esc(j.adjusted)}</p>` : ""}
      ${j.exact ? '<p class="ok small">= совпадает с эталоном — судья не вызывался</p>' : ""}` : ""}
    ${j && !j.available ? `<p class="warn">судья: ${esc(j.error)}</p>` : ""}
    ${b.given ? "" : `<details class="mt cmp" data-i="${i}" ${b.conflict ? "open" : ""}><summary>мой код | эталон</summary>
      <div class="sbs"><div><div class="muted">МОЙ КОД</div><div class="mine"></div></div><div><div class="muted">ЭТАЛОН</div><div class="theirs"></div></div></div>
    </details>`}
  </fieldset>`;
}

function testResult(t) {
  const [cls, txt] = TEST_ST[t.status];
  const vals = t.status === "fail" ? ` <span class="muted">эталон</span> <code>${esc(t.ref_value)}</code> <span class="muted">у вас</span> <code>${esc(t.user_value)}</code>` : "";
  return `<div class="test"><span class="${cls}">${txt}</span> ${esc(t.name)}${vals}${t.error ? ` <span class="muted">— ${esc(t.error)}</span>` : ""}</div>`;
}

function commonTests(rep) {
  const ts = rep.tests.filter(t => !t.block);
  if (!ts.length || (rep.blocks.length === 1 && rep.blocks[0].index == null)) return "";
  return `<fieldset class="box"><legend>ТЕСТЫ НА ВЕСЬ КОД</legend>${ts.map(testResult).join("")}</fieldset>`;
}

// ---------------- НАСТРОЙКИ ----------------
async function viewSettings() {
  const s = await api("/api/settings");
  view.innerHTML = `
    <fieldset class="box"><legend>ЭКРАН</legend>
      <label class="row"><input type="checkbox" id="crt" ${crtOn() ? "checked" : ""}> CRT-полосы (ретро-эффект, по умолчанию выключен)</label>
    </fieldset>
    <fieldset class="box"><legend>НОУТБУК</legend>
      <div class="row"><label>таймаут ячейки, с</label><input id="timeout" type="number" min="5" max="3600" value="${esc(s.cell_timeout)}" style="width:90px"></div>
    </fieldset>
    <fieldset class="box"><legend>ОЦЕНКА</legend>
      <p class="muted">блок = (Wвып·выполнение + Wтест·тесты + Wсуд·судья) / сумма весов доступных слоёв. Веса — любые неотрицательные числа.</p>
      <div class="row">
        <label>Wвып</label><input id="w_exec" type="number" min="0" value="${s.w_exec}" style="width:70px">
        <label>Wтест</label><input id="w_tests" type="number" min="0" value="${s.w_tests}" style="width:70px">
        <label>Wсуд</label><input id="w_judge" type="number" min="0" value="${s.w_judge}" style="width:70px">
      </div>
      <div class="row mt">
        <label>подсказка, −% блока</label><input id="hint_penalty" type="number" min="0" max="100" value="${s.hint_penalty}" style="width:70px">
        <label>план «с нуля», −% общей</label><input id="plan_penalty" type="number" min="0" max="100" value="${s.plan_penalty}" style="width:70px">
        <label>медленнее прошлого на, %</label><input id="slower_pct" type="number" min="0" value="${s.slower_pct}" style="width:70px">
      </div>
      <p class="muted small">Уровень: ≥90 легко · ≥70 нормально · ≥50 трудно · иначе забыл. Подсказки −1 уровень; время дольше прошлого раза (тот же режим) больше чем на указанный % — ещё −1. Новые веса применяются к следующим проверкам (и к «перепроверить»).</p>
    </fieldset>
    <fieldset class="box"><legend>LLM</legend>
      <div class="row"><label>провайдер</label>
        <select id="prov">
          <option value="ollama" ${s.llm_provider === "ollama" ? "selected" : ""}>Ollama (локально)</option>
          <option value="groq" ${s.llm_provider === "groq" ? "selected" : ""}>Groq API</option>
        </select></div>
      <h3 class="mt">ollama</h3>
      <div class="row"><label>url</label><input id="o-url" class="grow" value="${esc(s.ollama_url)}">
        <label>модель</label><input id="o-model" value="${esc(s.ollama_model)}"></div>
      <h3 class="mt">groq</h3>
      <div class="row"><label>модель</label><input id="g-model" class="grow" value="${esc(s.groq_model)}">
        <span class="${s.groq_key_set ? "ok" : "warn"}">GROQ_API_KEY ${s.groq_key_set ? "задан" : "не задан (.env)"}</span></div>
      <div class="row mt"><button id="test">проверить связь</button></div>
      <div class="log mt" id="out"></div>
    </fieldset>
    <button id="save" class="primary">сохранить настройки</button>
    <fieldset class="box mt"><legend>БЭКАП</legend>
      <p class="muted">Экспорт: один .zip — вся база (эталоны, версии, тесты, попытки, расписание, настройки) и исходники всех версий для чтения.
        Импорт заменяет текущую базу; она перед этим сохраняется в <code>data/backups/</code>.</p>
      <div class="row"><a class="btn" href="/api/backup/export" download>экспорт</a>
        <button id="imp">импорт…</button><input type="file" id="imp-file" accept=".zip" hidden>
        <button id="bk-now">автокопия сейчас</button></div>
      <p class="muted small mt">Автокопия SQLite делается раз в день, хранятся последние 7:</p>
      <div id="bk-list" class="log small"></div>
    </fieldset>`;
  const showBackups = list => {
    $("#bk-list").innerHTML = list.length ? list.map(b => `${esc(b.name)} <span class="muted">${(b.size / 1024).toFixed(0)} КБ · ${fmtDate(b.created)}</span>`).join("\n")
                                          : '<span class="muted">копий пока нет</span>';
  };
  api("/api/backup/list").then(showBackups);
  $("#bk-now").onclick = async () => {
    const r = await api("/api/backup/now", { method: "POST" });
    showBackups(r.backups); toast(r.made ? `создана ${r.made}` : "сегодняшняя копия уже есть");
  };
  $("#imp").onclick = () => $("#imp-file").click();
  $("#imp-file").onchange = async e => {
    const f = e.target.files[0];
    if (!f || !confirm(`Заменить текущую базу содержимым «${f.name}»?\nТекущая база будет сохранена в data/backups.`)) return;
    const fd = new FormData(); fd.append("file", f);
    try {
      const r = await api("/api/backup/import", { method: "POST", body: fd });
      toast(`импортировано эталонов: ${r.references} · прежняя база: ${r.previous_saved_as}`);
      api("/api/backup/list").then(showBackups);
    } catch (err) { toast(err.message, true); }
    e.target.value = "";
  };
  $("#crt").onchange = e => applyCrt(e.target.checked, true);
  const save = () => api("/api/settings", { method: "PUT", json: {
    llm_provider: $("#prov").value, ollama_url: $("#o-url").value, ollama_model: $("#o-model").value,
    groq_model: $("#g-model").value, cell_timeout: Math.max(5, +$("#timeout").value || 60),
    ...Object.fromEntries(["w_exec", "w_tests", "w_judge", "hint_penalty", "plan_penalty", "slower_pct"].map(k => [k, Math.max(0, +$("#" + k).value || 0)])) } });
  $("#save").onclick = async () => { await save(); toast("сохранено"); };
  $("#test").onclick = async () => {
    await save();
    $("#out").innerHTML = '<span class="cursor">спрашиваю модель</span>';
    const r = await api("/api/settings/test", { method: "POST" });
    $("#out").innerHTML = r.ok
      ? `<span class="ok">OK</span> · ${esc(r.provider)} · <b>${esc(r.model)}</b> · ответ за <b>${(r.ms / 1000).toFixed(1)} с</b>: «${esc(r.answer)}»`
      : `<span class="err">НЕТ СВЯЗИ:</span> ${esc(r.answer)}`;
  };
}
