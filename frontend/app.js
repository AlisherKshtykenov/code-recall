// CODE RECALL — экраны: «Сегодня», «Задачи», задача, решение (IDE), статистика, настройки.
const view = $("#view");
let current = null;  // открытая IDE — закрываем при уходе со страницы

const paintTheme = () => { $("#theme").innerHTML = ICON[{ dark: "moon", light: "sun", system: "system" }[themePref()] || "moon"]; };
$("#theme").onclick = () => { setTheme({ dark: "light", light: "system", system: "dark" }[themePref()] || "dark"); paintTheme(); };  // тёмная → светлая → как в системе
paintTheme();
// серия дней в верхней панели — из статистики (дней подряд со сданной попыткой)
function paintStreak() {
  api("/api/stats").then(st => {
    const n = st?.streak?.current || 0, el = $("#streak");
    el.hidden = !n;
    el.innerHTML = `${ICON.flame}${n} ${plural(n, "день", "дня", "дней")}`;
  }).catch(() => {});
}
paintStreak();

const routes = { today: viewToday, tasks: viewTasks, task: viewTask, attempt: viewAttempt, edit: viewEdit,
                 journal: viewJournal, review: viewReview, stats: viewStats, settings: viewSettings, assemble: viewAssemble, map: viewMap, builder: viewBuilder };
let lastHash = location.hash, skipRoute = false;
function route() {
  if (skipRoute) { skipRoute = false; return; }
  // из незаконченной попытки не уходим молча: она сохранится как брошенная
  if (current && current.leaveGuard && !current.leaveGuard()) {
    skipRoute = true;
    location.hash = lastHash;
    return;
  }
  lastHash = location.hash;
  if (current) { current.dispose(); current = null; }
  const [name, ...args] = location.hash.replace(/^#\/?/, "").split("/");
  const nav = { task: "tasks", attempt: "journal", edit: "tasks", review: "journal", assemble: "tasks", map: "map", builder: "builder" }[name] || name || "today";
  $$(".topbar nav a").forEach(a => a.classList.toggle("active", a.dataset.r === nav));
  document.body.classList.remove("ide-mode");
  view.innerHTML = '<div class="muted spinner">загрузка</div>';
  (routes[name] || viewToday)(...args).catch(e => { view.innerHTML = `<div class="card err">Ошибка: ${esc(e.message)}</div>`; });
}
window.addEventListener("hashchange", route);
route();

const STATUS = { solved: ["ok", "✓", "решено"], due: ["warn", "⟳", "пора повторить"], new: ["muted", "○", "новая"] };
const statusCell = s => { const [c, i, t] = STATUS[s] || STATUS.new; return `<span class="status-ico ${c}" title="${t}">${i}</span>`; };
const kindBadge = k => `<span class="badge ${k}">${KIND[k] || k}</span>`;

async function startAttempt(taskId, mode) {
  try {
    const t = normTask(await api(`/api/tasks/${taskId}`));
    mode = mode && t.modes.includes(mode) ? mode : t.default_mode;  // по умолчанию первым — «Библиотека»
    if (t.deps.length && !t.active_attempt) { location.hash = `#/assemble/${taskId}/${mode}`; return; }  // составная — сначала сборка
    const a = await api(`/api/tasks/${taskId}/attempts`, { method: "POST", json: { mode } });
    location.hash = `#/attempt/${a.id}`;
  } catch (e) { toast(e.message, true); }
}

// ---------------- Сегодня (стр. 16) ----------------
// причина из сервера: «… · сначала повтори кирпичик «X» · сначала освой применение (…)» -> текст + подсказки ↳
function splitReason(reason) {
  const parts = String(reason || "").split(" · ");
  const hints = parts.filter(p => /^сначала /.test(p) || /^сломано зависимостью/.test(p));
  return { text: parts.filter(p => !hints.includes(p)).join(" · "), hints };
}
async function viewToday() {
  const [t, st, all] = await Promise.all([api("/api/today"), api("/api/stats").catch(() => null), apiList("/api/tasks")]);
  const learn = Object.fromEntries(all.map(x => [x.id, Object.fromEntries(MODES.map(m => [m, x.mode_stats?.[m]?.learn || "none"]))]));
  const weak = [...t.overdue, ...t.due].filter(r => r.weak_brick);
  const overdue = t.overdue.filter(r => !r.weak_brick), due = t.due.filter(r => !r.weak_brick);
  const todo = [...overdue, ...due, ...weak];
  const known = todo.filter(r => r.median_ms), mins = Math.round(known.reduce((a, r) => a + r.median_ms, 0) / 60000);
  const byMode = m => todo.filter(r => r.mode === m).length;
  const first = todo[0] || t.new[0];
  const row = (r, opts = {}) => {
    const { text, hints } = splitReason(r.reason);
    return `<div class="trow2" data-id="${r.id}">
      <div class="tr-main"><div class="tr-name"><b class="mono">${esc(r.name || r.title)}</b>${opts.inline ? `<span class="faint"> · ${MODE_NAME[r.mode]}</span>` : ""}</div><div class="muted small">${esc(text)}</div>
        ${hints.map(h => `<div class="hint">↳ ${esc(h)}</div>`).join("")}</div>
      ${opts.compact ? "" : opts.mini ? catTag(r.category) : `${modeBadge(r.mode, { short: true })}${levelTag(r.level)}${catTag(r.category)}<span class="ms-slot">${modeHalves(learn[r.id])}</span>`}
      ${(sc => sc != null ? `<span class="score-b ${sc >= 70 ? "ok" : sc >= 50 ? "warn" : "err"}">${sc}</span>` : "")(opts.scoreOf?.(r))}
      ${opts.button ? `<button class="small" data-go="${r.id}" data-mode="${r.mode}">${opts.button}</button>` : `<span class="chev" data-go="${r.id}" data-mode="${r.mode}">${ICON.chevron}</span>`}</div>`;
  };
  const card = (title, dot, items, opts = {}) => items.length ? `<section class="tcard"><header><i class="dot-${dot}"></i><h2>${title}</h2><span class="faint">${items.length}</span>
      ${opts.note ? `<span class="grow"></span><span class="faint small">${opts.note}</span>` : ""}</header>${items.map(r => row(r, opts)).join("")}</section>` : "";
  const cal = arr(st?.calendar).slice(-12);
  const today = new Date();
  view.innerHTML = `<div class="today">
    <div class="today-head"><div>
      <div class="muted">${today.toLocaleDateString("ru", { weekday: "long", day: "numeric", month: "long" }).replace(/^./, c => c.toUpperCase())}</div>
      <h1 class="big">${todo.length ? `На сегодня ${todo.length} ${plural(todo.length, "задача", "задачи", "задач")}${mins ? ` · около ${mins} ${plural(mins, "минуты", "минут", "минут")}` : ""}` : "На сегодня повторений нет"}</h1>
      <div class="row">${overdue.length ? `<span class="badge dot err">${overdue.length} просрочено</span>` : ""}${due.length ? `<span class="badge dot warn">${due.length} по плану</span>` : ""}
        ${t.new.length ? `<span class="badge dot new">${t.new.length} ${plural(t.new.length, "новая", "новые", "новых")}</span>` : ""}
        ${todo.length ? `<span class="faint">по режимам:</span>${byMode("library") ? `<span class="mb mb-lib">${ICON.book}${byMode("library")}</span>` : ""}${byMode("scratch") ? `<span class="mb mb-scr">${ICON.gear}${byMode("scratch")}</span>` : ""}` : ""}</div></div>
      <span class="grow"></span>
      <div class="streak-card">${st ? `<div><b class="num">${st.streak.current}</b> ${plural(st.streak.current, "день", "дня", "дней")} подряд
          <div class="sq-row">${cal.map(d => `<i class="${d.count ? "on" : ""}" title="${d.date}: ${d.count}"></i>`).join("")}</div></div>` : ""}
        ${first ? `<button class="primary" id="go-first">${ICON.play}Начать первую — ${esc(first.name || first.title)} · ${MODE_NAME[first.mode]}</button>` : ""}</div>
    </div>
    ${!todo.length && !t.reviews.length ? `<div class="card">${emptyState({ icon: "check", tone: "ok", title: "На сегодня всё",
        text: `${t.upcoming.length ? `Ближайшие 7 дней ждут ${t.upcoming.length} ${plural(t.upcoming.length, "задача", "задачи", "задач")}.` : ""}`,
        actions: `${t.new[0] ? `<button id="take-new">Взять новую — ${esc(t.new[0].name || t.new[0].title)}</button>` : ""}<a class="btn link" href="#/stats">Статистика</a>` })}</div>` : ""}
    <div class="today-cols"><div>
      ${t.reviews.length ? `<section class="tcard"><header><i class="dot-due"></i><h2>Работа над ошибками</h2><span class="faint">${t.reviews.length}</span></header>
        ${t.reviews.map(r => `<div class="trow2" data-review="${r.id}"><div class="tr-main"><b>${esc(r.title)}</b><div class="muted small">${esc(r.reason)}</div></div>${modeBadge(r.mode, { short: true })}<button class="small primary">Продолжить</button></div>`).join("")}</section>` : ""}
      ${card("Просрочено", "fail", overdue, { cls: "due" })}
      ${card("На сегодня", "due", due, { cls: "due" })}
    </div><div>
      ${card("Слабые кирпичики", "fail", weak, { compact: true, inline: true, button: "Повторить", note: "из ошибок в больших задачах", scoreOf: r => r.last_score })}
      ${card("Новые", "new", t.new.slice(0, 8), { mini: true, inline: true })}${t.new.length > 8 ? `<p class="faint small">и ещё ${t.new.length - 8} — в <a href="#/tasks">Задачах</a></p>` : ""}
      ${t.upcoming.length ? `<details class="tcard"><summary><i class="dot-plan"></i><h2>Ближайшие 7 дней</h2><span class="faint">${t.upcoming.length}</span></summary>${t.upcoming.map(r => row(r, { cls: "solved" })).join("")}</details>` : ""}
      ${todo.length ? '<p class="faint small">Порядок: сначала кирпичики, потом собранное из них; по каждой задаче — сначала применение, потом устройство.</p>' : ""}
    </div></div></div>`;
  $$("[data-go]").forEach(b => b.onclick = e => { e.stopPropagation(); startAttempt(b.dataset.go, b.dataset.mode); });
  $$(".trow2[data-id]").forEach(tr => tr.onclick = () => { location.hash = `#/task/${tr.dataset.id}`; });
  $$(".trow2[data-review]").forEach(tr => tr.onclick = () => { location.hash = `#/review/${tr.dataset.review}`; });
  const gf = $("#go-first");
  if (gf) gf.onclick = () => startAttempt(first.id, first.mode);
  const tn = $("#take-new");
  if (tn) tn.onclick = () => startAttempt(t.new[0].id, t.new[0].mode);
}

// ---------------- Задачи (стр. 17) ----------------
const lib = { q: "", mode: "", status: "", tags: [], topic: undefined, sort: "title", dir: 1 };
// повтор: ближайший срок из режимов задачи
function nextDue(t) {
  const st = t.modes.map(m => t.mode_stats?.[m] || {}), today = new Date().toISOString().slice(0, 10);
  const od = Math.max(0, ...st.map(s => s.overdue_days || 0));
  if (od) return [`просрочено ${od} дн`, "warn", -od];
  const dues = st.map(s => s.due_at).filter(Boolean).sort();
  if (!dues.length) return ["не начата", "faint", 9e9];
  return dues[0] === today ? ["сегодня", "", 0] : [fmtDay(dues[0]), "", Date.parse(dues[0]) / 864e5];
}
async function viewTasks() {
  // дерево тем — необязательная часть: не загрузилось — библиотека всё равно открывается, без дерева
  const [rawTasks, topics, planned] = await Promise.all([api("/api/tasks"), apiList("/api/topics"), apiList("/api/map/planned")]);
  const tasks = arr(rawTasks).map(normTask);
  lib.topic ??= store.get("lib.topic", null);
  if (lib.topic != null && !topics.some(t => t.id === lib.topic)) lib.topic = null;
  const allTags = [...new Set(tasks.flatMap(t => t.tags))].filter(g => !["стена", "блок"].includes(g)).sort();
  const learn = (t, m) => t.mode_stats?.[m]?.learn || "none";
  tasks.forEach(t => {
    t.topic = topicPath(topics, t.topic_id); t.category = t.mode_stats?._category;
    t.learn = Object.fromEntries(MODES.map(m => [m, learn(t, m)]));
    [t.dueText, t.dueCls, t.dueKey] = nextDue(t);
    t.bestKey = Math.max(-1, ...MODES.map(m => t.mode_stats?.[m]?.best ?? -1));
  });
  const cols = [["name", "Название"], ["level", "Уровень"], ["category", "Тема"], ["", "Теги"], ["", "Статус: библиотека | с нуля"], ["bestKey", "Лучшая"], ["dueKey", "Повтор"]];
  view.innerHTML = `
    <div class="row page-head"><div><h1>Задачи</h1><div class="muted">${tasks.length} ${plural(tasks.length, "задача", "задачи", "задач")} · у каждой два режима: <span class="accent">библиотека</span> и с нуля</div></div>
      <span class="grow"></span><button id="upload">${ICON.upload}Загрузить папки</button><button class="primary" id="new">${ICON.plus}Новая задача</button></div>
    <div class="libgrid ${store.get("lib.treeHidden", false) ? "tree-hidden" : ""}" id="libgrid">
      <div class="card libtree" id="tree"></div>
      <div class="card lib-main" style="min-width:0">
        <div class="lib-filters">
          <button class="icon-btn" id="tree-toggle" title="показать / скрыть дерево тем">${ICON.panel}</button>
          <label class="pal-search lib-q">${ICON.search}<input id="q" placeholder="Поиск по названию" value="${esc(lib.q)}"><kbd>/</kbd></label>
          <div class="row" style="gap:6px"><button class="fchip ${lib.tags.length ? "" : "sel"}" data-tag="">все теги</button>${allTags.slice(0, 8).map(g => `<button class="fchip ${lib.tags.includes(g) ? "sel" : ""}" data-tag="${esc(g)}">${esc(g)}</button>`).join("")}</div>
          <span class="grow"></span>
          <div class="seg" style="margin:0">${[["", "оба режима"], ["library", "библиотека"], ["scratch", "с нуля"]].map(([k, n]) => `<button data-fm="${k}" class="${lib.mode === k ? "sel" : ""}">${n}</button>`).join("")}</div>
          <div class="seg" style="margin:0">${[["", "Все"], ["due", "Пора"], ["weak", "Слабые"], ["new", "Новые"], ["planned", "План"]].map(([k, n]) => `<button data-fs="${k}" class="${lib.status === k ? "sel" : ""}">${n}</button>`).join("")}</div>
        </div>
        <div class="scroll-x"><table class="lib-table"><thead><tr>${cols.map(([k, n]) => `<th class="${k ? "sort" : ""}" data-k="${k}">${n}${k && lib.sort === k ? (lib.dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead>
          <tbody id="rows"></tbody></table></div>
        <div class="faint small lib-foot" id="lib-foot"></div>
      </div></div>`;
  if (!tasks.length) {
    $("#libgrid").outerHTML = `<div class="card">${emptyState({ icon: "blocks", title: "Пока ни одной задачи",
      text: "Задача — это эталон, тесты и описание. Начни с маленького кирпичика вроде <span class=\"mono\">relu</span> или загрузи карту навыков, чтобы увидеть, что запланировано.",
      actions: '<button class="primary" id="new2">Новая задача</button><a class="btn" href="#/settings">Импорт карты навыков</a>' })}</div>`;
    $("#new2").onclick = () => { location.hash = "#/builder"; };
  }
  let kids = {};
  const render = () => {
    if (!$("#rows")) return;
    const inTopic = lib.topic == null ? null : new Set(subtreeIds(kids, lib.topic));
    const modes = lib.mode ? [lib.mode] : MODES;
    const rows = tasks.filter(t => lib.status !== "planned" && (!lib.mode || t.modes.includes(lib.mode))
        && (!lib.status || modes.some(m => t.learn[m] === lib.status))
        && (!inTopic || inTopic.has(t.topic_id)) && lib.tags.every(g => t.tags.includes(g))
        && (t.title + " " + t.name + " " + t.topic + " " + t.tags.join(" ")).toLowerCase().includes(lib.q.toLowerCase()))
      .sort((a, b) => {
        const x = a[lib.sort], y = b[lib.sort];
        if (x == null) return 1; if (y == null) return -1;
        return (typeof x === "string" ? x.localeCompare(y) : x - y) * lib.dir;
      });
    const plan = (lib.status && lib.status !== "planned") || lib.mode || lib.tags.length ? [] : planned.filter(p => (!inTopic || inTopic.has(p.topic_id))
      && (p.name + " " + p.note + " " + arr(p.categories).join(" ")).toLowerCase().includes(lib.q.toLowerCase()));
    const best = t => MODES.map(m => t.mode_stats?.[m]?.best ?? "—").join('<span class="faint"> | </span>');
    $("#rows").innerHTML = rows.map(t => `<tr class="link" data-id="${t.id}" draggable="true" title="${esc(t.title)} — перетащите на узел дерева, чтобы перенести">
      <td><span class="mono title">${esc(t.name)}</span>${t.active_attempt ? ' <span class="badge warn">в процессе</span>' : ""}${t.broken ? ` <span class="badge err" title="${esc(t.broken)}">сломано</span>` : ""}</td>
      <td>${levelTag(t.level)}</td><td>${t.category ? catTag(t.category) : '<span class="faint">—</span>'}</td>
      <td><div class="row" style="gap:4px;flex-wrap:nowrap">${t.tags.filter(g => !["стена", "блок"].includes(g)).slice(0, 1).map(g => `<span class="tag">${esc(g)}</span>`).join("")}</div></td>
      <td>${t.modes.length ? modePair(t.learn) : '<span class="badge plan">концепт</span>'}</td>
      <td class="nowrap mono-num">${best(t)}</td><td class="nowrap ${t.dueCls}">${t.dueText}</td></tr>`).join("")
      + plan.map(p => `<tr class="link planned" data-plan="${esc(p.name)}" title="кирпичик карты — задачи ещё нет; клик — создать">
        <td><span class="mono title">${esc(p.name)}</span></td><td><span class="faint">—</span></td><td>${arr(p.categories)[0] ? catTag(p.categories[0]) : ""}</td><td></td>
        <td><span class="badge plan">${p.kind === "concept" ? "концепт" : "план"}</span></td><td class="faint">—</td><td class="faint small">в ${p.rows.length} стр. карты</td></tr>`).join("")
      || `<tr><td colspan="7">${emptyState({ icon: "search", title: "Ничего не найдено", text: "Сбросьте фильтры или поиск." })}</td></tr>`;
    $("#lib-foot").textContent = `Показано ${rows.length} из ${tasks.length}${plan.length ? ` · запланировано ${plan.length}` : ""}`;
    $$("#rows tr[data-id]").forEach(tr => tr.ondragstart = e => e.dataTransfer.setData("text/task", tr.dataset.id));
  };
  // выбор узла — перерисовать дерево и таблицу; правка дерева (создать, перенести…) — перечитать всё
  const onTree = (reload = true) => { if (reload) return viewTasks(); kids = renderTopicTree($("#tree"), topics, lib, onTree); render(); };
  if ($("#tree")) kids = renderTopicTree($("#tree"), topics, lib, onTree);
  render();
  if (!$("#rows")) { $("#upload").onclick = uploadDialog; $("#new").onclick = () => { location.hash = "#/builder"; }; return; }
  $("#tree-toggle").onclick = () => { const g = $("#libgrid"); g.classList.toggle("tree-hidden"); store.set("lib.treeHidden", g.classList.contains("tree-hidden")); };
  $$("[data-tag]").forEach(b => b.onclick = () => { const g = b.dataset.tag; lib.tags = !g ? [] : lib.tags.includes(g) ? lib.tags.filter(x => x !== g) : [...lib.tags, g]; viewTasks(); });
  $$("[data-fm]").forEach(b => b.onclick = () => { lib.mode = b.dataset.fm; $$("[data-fm]").forEach(x => x.classList.toggle("sel", x === b)); render(); });
  $$("[data-fs]").forEach(b => b.onclick = () => { lib.status = b.dataset.fs; $$("[data-fs]").forEach(x => x.classList.toggle("sel", x === b)); render(); });
  $("#q").oninput = e => { lib.q = e.target.value; render(); };
  const slash = e => { if (!document.body.contains($("#q") || document.createElement("i"))) return document.removeEventListener("keydown", slash);
    if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) { e.preventDefault(); $("#q").focus(); } };
  document.addEventListener("keydown", slash);
  $$("th.sort").forEach(th => th.onclick = () => { lib.dir = lib.sort === th.dataset.k ? -lib.dir : 1; lib.sort = th.dataset.k; viewTasks(); });
  $("#rows").onclick = e => {
    const tr = e.target.closest("tr[data-id]"), pl = e.target.closest("tr[data-plan]");
    if (tr) location.hash = `#/task/${tr.dataset.id}`;
    if (pl) { const p = planned.find(x => x.name === pl.dataset.plan); openChip({ ...p, status: "planned" }); }
  };
  $("#upload").onclick = uploadDialog;
  $("#new").onclick = () => { location.hash = "#/builder"; };  // конструктор — визуальная доска
}

// Загрузка: перетащить папку задачи (или несколько) -> предпросмотр -> сохранить
function uploadDialog() {
  const back = document.createElement("div");
  back.className = "modal-back";
  back.innerHTML = `<div class="modal"><div class="row"><h2 style="margin:0">Загрузить задачи</h2><span class="grow"></span><button class="icon-btn" data-x>✕</button></div>
    <p class="muted small">Перетащите папку задачи целиком (или несколько). Внутри: <code>reference/*.py</code> — эталон, <code>tests/test_*.py</code> — тесты,
      необязательно <code>description.md</code>, <code>task.json</code>, <code>starter/</code> (заготовки), <code>data/</code> (датасеты). Повторная загрузка той же папки — новая версия.</p>
    <div class="drop" id="drop">Перетащите папки сюда<br><span class="small">или <a href="#" id="pick">выберите папку</a></span></div>
    <input type="file" id="pick-dir" webkitdirectory multiple hidden>
    <div id="pv" class="mt"></div></div>`;
  document.body.appendChild(back);
  const close = () => back.remove();
  $("[data-x]", back).onclick = close;
  back.onclick = e => { if (e.target === back) close(); };
  const drop = $("#drop", back);
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = async e => { e.preventDefault(); drop.classList.remove("over"); preview(await collectDrop(e.dataTransfer)); };
  $("#pick", back).onclick = e => { e.preventDefault(); $("#pick-dir", back).click(); };
  $("#pick-dir", back).onchange = e => preview([...e.target.files].filter(f => !SKIP.test(f.webkitRelativePath)).map(f => ({ file: f, path: f.webkitRelativePath })));
  const form = items => { const fd = new FormData(); items.forEach(it => { fd.append("files", it.file); fd.append("paths", it.path); }); return fd; };
  async function preview(items) {
    const pv = $("#pv", back);
    if (!items.length) { pv.innerHTML = '<p class="err">файлов нет</p>'; return; }
    pv.innerHTML = `<div class="muted spinner">разбираю ${items.length} файлов</div>`;
    let res;
    try { res = await api("/api/tasks/upload/preview", { method: "POST", body: form(items) }); }
    catch (e) { pv.innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    const lbl = { new: ["ok", "новая"], changed: ["warn", "новая версия"], unchanged: ["muted", "без изменений"], error: ["err", "ошибка"], slot: ["ok", "слот"] };
    pv.innerHTML = res.map(r => `<div class="card" style="box-shadow:none;border:1px solid var(--line);margin-bottom:8px">
        <div class="row"><span class="badge ${lbl[r.status][0]}">${lbl[r.status][1]}</span><b>${esc(r.folder)}</b>
          ${r.version ? `<span class="muted small">v${r.version}${r.status === "changed" ? ` → v${r.version + 1}` : ""}</span>` : ""}
          ${r.data_files ? `<span class="muted small">+ ${r.data_files} файлов в data/</span>` : ""}</div>
        ${r.error ? `<div class="err small mt">${esc(r.error)}</div>` : ""}
        ${r.files ? `<div class="muted small mt">${r.files.map(esc).join(" · ")}</div>` : ""}
        ${r.status === "changed" ? `<div class="small mt">${r.added.length ? `<span class="ok">+ ${r.added.map(esc).join(", ")}</span><br>` : ""}${r.removed.length ? `<span class="err">− ${r.removed.map(esc).join(", ")}</span><br>` : ""}
          ${r.changed.map(f => `<details><summary>изменён ${esc(f)}</summary><div class="diff">${diffHtml(r.diff[f])}</div></details>`).join("")}</div>` : ""}
      </div>`).join("") + `<div class="row mt"><span class="grow"></span><button data-x>Отмена</button>
        <button class="primary" id="save" ${res.some(r => ["new", "changed", "slot"].includes(r.status)) ? "" : "disabled"}>Сохранить</button></div>`;
    $$("[data-x]", back).forEach(b => b.onclick = close);
    $("#save", back).onclick = async () => {
      try {
        const out = await api("/api/tasks/upload", { method: "POST", body: form(items) });
        toast(out.map(o => `${o.folder}: ${{ created: "создана", new_version: `версия ${o.version}`, unchanged: "без изменений", slot: `слот ${o.slot}` }[o.status] || o.error}`).join(" · "), out.some(o => o.status === "error"));
        close(); viewTasks();
      } catch (e) { toast(e.message, true); }
    };
  }
}

// ---------------- Страница задачи ----------------
// статус изучения режима (как на карте) -> бейдж
const LEARN = { learned: ["ok", "выучено"], due: ["warn", "пора"], weak: ["err", "слабо"], new: ["new", "новое"], none: ["plan", "нет режима"] };
const fmtDay = iso => iso ? new Date(iso).toLocaleDateString("ru", { day: "numeric", month: "short" }).replace(".", "") : "";
const fmtMin = ms => ms ? `${Math.max(1, Math.round(ms / 60000))} ${plural(Math.max(1, Math.round(ms / 60000)), "минута", "минуты", "минут")}` : "";
// README по разделам: вступление, «Как применять», «Как работает», остальное
function splitReadme(text) {
  const parts = { intro: "", apply: "", how: "", rest: "" };
  let cur = "intro";
  for (const line of String(text || "").split("\n")) {
    const h = /^##\s+(.+)/.exec(line);
    if (h) cur = /как применять/i.test(h[1]) ? "apply" : /как работает/i.test(h[1]) ? "how" : "rest";
    if (h && (cur === "apply" || cur === "how")) continue;
    parts[cur] += line + "\n";
  }
  parts.intro = parts.intro.replace(/^#\s+.+\n/, "");  // заголовок — уже в шапке
  return parts;
}

async function viewTask(id, tab = "about") {
  const [t0, topics] = await Promise.all([api(`/api/tasks/${id}`), apiList("/api/topics")]);
  const t = normTask(t0);
  const ms = t.mode_stats || {}, cat = ms._category;
  let mode = store.get(`mode.${t.id}`, t.default_mode);
  if (!t.modes.includes(mode)) mode = t.default_mode;
  const crumbs = ["Задачи", ...(t.topic_id ? topicPath(topics, t.topic_id).split(" / ") : [])];
  const modeCard = m => {
    const s = ms[m] || {}, [cls, word] = LEARN[s.learn] || LEARN.none, on = t.modes.includes(m);
    const pct = s.last != null ? s.last : 0, bar = { ok: "var(--ok)", warn: "var(--due)", err: "var(--fail)" }[cls] || "var(--new)";
    return `<button class="mode-card ${on ? "" : "off"} ${m === mode ? "sel" : ""}" data-mode="${m}" ${on ? "" : "disabled"}>
      <div class="row">${modeBadge(m)}<span class="muted">${m === "library" ? "как и где применять" : "как устроено внутри"}</span><span class="grow"></span><span class="badge dot ${cls}">${on ? word : "нет режима"}</span></div>
      ${on ? `<div class="mc-bar"><i style="width:${pct}%;background:${bar}"></i></div>
      <div class="mc-stats">${s.best != null ? `<span>лучшее <b>${s.best}</b></span>` : '<span class="faint">ещё не сдавал</span>'}
        ${s.last != null && s.last !== s.best ? `<span>последнее <b>${s.last}</b></span>` : ""}${s.reps ? `<span>повторов <b>${s.reps}</b></span>` : ""}
        ${s.overdue_days ? `<span class="warn">просрочено на ${s.overdue_days} ${plural(s.overdue_days, "день", "дня", "дней")}</span>` : s.due_at ? `<span>следующий <b>${fmtDay(s.due_at)}</b></span>` : ""}</div>` : ""}
    </button>`;
  };
  view.innerHTML = `<div class="task-page">
    <div class="crumbs page-crumbs">${crumbs.map((c, i) => i ? esc(c) : '<a href="#/tasks">Задачи</a>').join('<span class="sep">/</span>')}</div>
    <div class="row task-head"><h1 class="mono">${esc(t.name)}</h1>${levelTag(t.level)}${cat ? catTag(cat) : ""}${t.tags.filter(g => !["стена", "блок"].includes(g)).map(g => `<span class="tag">${esc(g)}</span>`).join("")}
      <span class="grow"></span><a class="btn link" href="#/edit/${t.id}">Редактировать</a><button class="link" id="dup" title="копия задачи со всеми файлами">Дублировать</button>
      <a class="btn link" href="#/builder/${t.id}">Открыть в конструкторе</a></div>
    <p class="muted task-sub">${esc(t.title)}</p>
    ${t.broken ? `<div class="alert err"><b>Сломано зависимостью</b> — ${esc(t.broken)}<p class="muted small">Тесты задачи упали на эталоне после смены эталона кирпичика; такие тесты не влияют на оценку.</p>
      <button class="small" id="recheck">Перепроверить</button></div>` : ""}
    ${t.modes.length ? `${MODES.map(modeCard).join("")}
      <button class="primary go-big" id="go"></button><div class="faint small go-note" id="go-note"></div>`
      : `<div class="card">${emptyState({ icon: "book", title: "Концепт", text: "Только README — без эталона и тестов, в повторения не входит." })}</div>`}
    <div class="tabs">${[["about", "README"], ["attempts", `Попытки <span class="faint">${t.attempts || ""}</span>`], ["compose", "Состав"], ["versions", "Версии"], ["settings", "Настройки"]]
      .map(([k, n]) => `<a href="#/task/${id}/${k}" class="${k === tab ? "active" : ""}">${n}</a>`).join("")}</div>
    <div id="tab"></div></div>`;
  const paint = () => {
    $$(".mode-card").forEach(b => b.classList.toggle("sel", b.dataset.mode === mode));
    const go = $("#go");
    if (!go) return;
    go.innerHTML = `${ICON.play}${t.deps.length ? "Собрать и начать" : "Начать"} · ${MODE_NAME[mode]}`;
    const s = ms[mode] || {};
    $("#go-note").textContent = s.median_ms ? `≈ ${fmtMin(s.median_ms)} — обычно столько` : "";
  };
  $$(".mode-card:not(.off)").forEach(b => b.onclick = () => { mode = b.dataset.mode; store.set(`mode.${t.id}`, mode); paint(); });
  paint();
  const go = $("#go");
  if (go) go.onclick = () => startAttempt(t.id, mode);
  $("#dup").onclick = async e => {  // копия под новым названием; кнопка заблокирована, пока идёт запрос
    const title = prompt("Название новой задачи (копия всех файлов этой задачи)", "");
    if (!title || !title.trim()) return;
    if (title.trim() === t.title) return toast("название должно отличаться от исходной задачи", true);
    e.currentTarget.disabled = true;
    try { const r = await api(`/api/tasks/${t.id}/duplicate`, { method: "POST", json: { title: title.trim() } }); toast(`создана «${title.trim()}»`); location.hash = `#/task/${r.id}`; }
    catch (err) { toast(err.message, true); $("#dup").disabled = false; }
  };
  const rc = $("#recheck");
  if (rc) rc.onclick = async () => { rc.disabled = true; const { job } = await api(`/api/tasks/${t.id}/recheck`, { method: "POST" }); await followJob(job, () => {}); viewTask(id, tab); };
  const box = $("#tab");
  if (tab === "compose") return renderComposition(box, id);
  if (tab === "about") {
    if (!t.description) { box.innerHTML = `<div class="card">${emptyState({ icon: "files", title: "Описания нет", text: "Добавьте description.md в редакторе задачи.", actions: `<a class="btn" href="#/edit/${t.id}">Открыть редактор</a>` })}</div>`; return; }
    const r = splitReadme(t.description);
    let meta = {};
    try { meta = JSON.parse((await api(`/api/tasks/${t.id}/file?path=task.json`)).content); } catch { meta = {}; }
    const rules = [
      ...arr(meta.required_names).map(n => `<span class="chip-n">библиотека: ${esc(n)}</span>`),
      ...[...arr(meta.forbidden_modules), ...arr(meta.forbidden_names)].map(n => `<span class="chip-n bad">нельзя с нуля: ${esc(n)}</span>`)];
    box.innerHTML = `${r.intro.trim() ? `<div class="card"><div class="md">${md(r.intro)}</div></div>` : ""}
      ${r.apply.trim() || r.how.trim() ? `<div class="readme-cols">
        <section class="rcard"><header>${ICON.book}<h2>Как применять</h2></header><div class="md">${r.apply.trim() ? md(r.apply) : '<p class="muted">раздела нет</p>'}</div></section>
        <section class="rcard how"><header><span class="mi mi-scr">${ICON.gear}</span><h2>Как работает</h2></header><div class="md">${r.how.trim() ? md(r.how) : '<p class="muted">раздела нет</p>'}</div>
          ${rules.length ? `<div class="label mt">Правила режима</div><div class="chips">${rules.join("")}</div>` : ""}</section></div>` : ""}
      ${r.rest.trim() ? `<div class="card"><div class="md">${md(r.rest)}</div></div>` : ""}
      <div class="card"><div class="label">Файлы и зависимости</div>
        <div class="chips">${t.reference.map(f => `<span class="chip-n">${esc(f)} · ${t.roles[f] === "given" ? "дан" : "пишу сам"}</span>`).join("")}</div>
        <div class="muted small mt">тестов: ${t.test_files.length || "нет"} · лимит времени ${t.timeout} с · версия ${t.version}${t.dirty ? ' · <span class="warn">в папке есть несохранённые изменения</span>' : ""}</div>
        ${t.deps.length ? `<div class="mt">${t.deps.map(d => `<div class="small mono">${d.slot ? `from slots.${esc(d.slot)} import …  <span class="muted">(слот: реализация выбирается при сборке)</span>` : `from bricks.${esc(d.name)} import …  <span class="muted">← ${esc(d.task)}</span>`}</div>`).join("")}</div>` : ""}</div>`;
  } else if (tab === "attempts") {
    box.innerHTML = '<div class="card" id="jr"></div><div class="card" id="hist-card" hidden><h3>Оценка и время по попыткам</h3><div id="hist"></div></div>';
    const rows = await journalTable($("#jr"), { task_id: id });
    const done = rows.filter(r => r.type === "attempt" && r.score != null).reverse();
    if (done.length) { $("#hist-card").hidden = false; historyCharts($("#hist"), done.map(a => ({ date: a.finished_at, score: a.score, total_ms: a.total_ms }))); }
  } else if (tab === "versions") {
    box.innerHTML = `<div class="card"><table><thead><tr><th>Версия</th><th>Загружена</th><th>Файлы</th><th></th></tr></thead><tbody>
      ${[...t.versions].reverse().map(v => `<tr><td>v${v.number}${v.number === t.version ? ' <span class="badge ok">текущая</span>' : ""}</td><td class="muted">${fmtDate(v.created_at)}</td>
        <td class="muted small">${v.files.length}</td><td>${v.number > 1 ? `<button class="small ghost" data-d="${v.number}">diff с v${v.number - 1}</button>` : ""}</td></tr>`).join("")}</tbody></table><div id="vd" class="mt"></div></div>`;
    $$("[data-d]", box).forEach(b => b.onclick = async () => {
      const n = +b.dataset.d, d = await api(`/api/tasks/${id}/diff?a=${n - 1}&b=${n}`);
      $("#vd").innerHTML = Object.entries(d).map(([f, txt]) => `<div class="label mt">${esc(f)}</div><div class="diff">${diffHtml(txt)}</div>`).join("") || '<p class="muted">различий нет</p>';
    });
  } else if (tab === "settings") taskSettings(t, box);
}

function taskSettings(t, box) {
  box.innerHTML = `
    <div class="card"><h3>Задача</h3>
      <div class="row"><label>Название</label><input id="s-title" class="grow" value="${esc(t.title)}">
        <label>Тип</label><select id="s-kind"><option value="algo" ${t.kind === "algo" ? "selected" : ""}>Алгоритм</option><option value="ml" ${t.kind === "ml" ? "selected" : ""}>ML</option></select>
        <label>Узел</label><select id="s-topic"></select></div>
      <div class="row mt"><label>Теги</label><input id="s-tags" class="grow" value="${esc(t.tags.join(", "))}" placeholder="через запятую"></div>
      <div class="row mt"><label>Лимит времени на запуск и тесты, с</label><input id="s-timeout" type="number" min="5" value="${t.timeout}" style="width:100px">
        <span class="muted small">для ML можно 600+</span></div>
      <div class="row mt"><button class="primary" id="s-save">Сохранить</button><span class="grow"></span><button class="danger" id="s-del">Удалить задачу</button></div></div>
    <div class="card"><h3>Роли файлов эталона</h3>
      <p class="muted small">«Пишу сам» — в попытке файл пустой (или с заготовкой из starter/). «Дан» — копируется в попытку как есть.</p>
      ${t.reference.map(f => `<div class="row" style="padding:4px 0"><span class="mono grow">${esc(f)}</span>
        <select data-role="${esc(f)}"><option value="write" ${t.roles[f] !== "given" ? "selected" : ""}>пишу сам</option><option value="given" ${t.roles[f] === "given" ? "selected" : ""}>дан</option></select></div>`).join("")}
      <button class="mt" id="r-save">Сохранить роли (новая версия)</button></div>
    <div class="card"><h3>Окружение Python</h3>
      <p class="muted small">Путь к .venv, к папке проекта с .venv или к python. Пусто — окружение приложения. Нужен pytest.</p>
      <div class="row"><input id="py" class="grow" value="${esc(t.python)}" placeholder="~/projects/course/.venv"><button id="py-check">Проверить</button><button id="py-save" class="primary">Сохранить</button></div>
      <div id="py-out" class="small muted mt">сейчас: <span class="mono">${esc(t.python_resolved)}</span></div></div>
    <div class="card"><h3>Данные</h3>
      ${t.data_link ? `<p>data/ подключена к папке <span class="mono">${esc(t.data_link)}</span> — файлы не копируются.</p><button id="unbind">Отключить</button>`
        : `<p class="muted small">Большие датасеты не нужно копировать: подключите папку на диске — data/ станет ссылкой на неё.</p>
           <div class="row"><input id="bind-path" class="grow" placeholder="/Users/me/datasets/cifar10"><button id="bind">Подключить как data/</button></div>`}
      <p class="muted small mt">Папка задачи: <span class="mono">${esc(t.path)}</span></p></div>`;
  $("#s-save").onclick = async () => {
    try { await api(`/api/tasks/${t.id}`, { method: "PATCH", json: { title: $("#s-title").value, kind: $("#s-kind").value, timeout: +$("#s-timeout").value,
      tags: $("#s-tags").value.split(",").map(x => x.trim()).filter(Boolean), ...($("#s-topic").value ? { topic_id: +$("#s-topic").value } : {}) } }); toast("сохранено"); }
    catch (e) { toast(e.message, true); }
  };
  apiList("/api/topics").then(tp => { $("#s-topic").innerHTML = '<option value="">— без узла —</option>' + topicOptions(tp, t.topic_id); });
  $("#s-del").onclick = async () => {
    if (!confirm(`Удалить «${t.title}» со всеми версиями и попытками? Подключённая папка с данными не пострадает.`)) return;
    await api(`/api/tasks/${t.id}`, { method: "DELETE" }); location.hash = "#/tasks";
  };
  $("#r-save").onclick = async () => {
    const roles = Object.fromEntries($$("[data-role]").map(s => [s.dataset.role, s.value]));
    try { const r = await api(`/api/tasks/${t.id}/roles`, { method: "PUT", json: { roles } }); toast(r.status === "unchanged" ? "роли не изменились" : `версия ${r.version}`); }
    catch (e) { toast(e.message, true); }
  };
  const pyOut = $("#py-out");
  $("#py-check").onclick = async () => {
    try {
      const r = await api("/api/python/check", { method: "POST", json: { path: $("#py").value.trim() } });
      pyOut.className = "small mt";
      pyOut.innerHTML = `<span class="mono">${esc(r.python)}</span> · Python ${esc(r.version)} · ${r.packages.map(esc).join(", ") || "пакетов не найдено"}`
        + (r.pytest ? "" : `<div class="err mt">нет pytest — установите: <span class="mono">${esc(r.fix)}</span></div>`);
    } catch (e) { pyOut.className = "small mt err"; pyOut.textContent = e.message; }
  };
  $("#py-save").onclick = async () => {
    try { await api(`/api/tasks/${t.id}`, { method: "PATCH", json: { python: $("#py").value.trim() } }); toast("окружение сохранено"); }
    catch (e) { pyOut.className = "small mt err"; pyOut.textContent = e.message; }
  };
  const bind = $("#bind"), unbind = $("#unbind");
  if (bind) bind.onclick = async () => {
    try { await api(`/api/tasks/${t.id}/data/bind`, { method: "POST", json: { path: $("#bind-path").value.trim() } }); toast("папка подключена"); viewTask(t.id, "settings"); }
    catch (e) { toast(e.message, true); }
  };
  if (unbind) unbind.onclick = async () => {
    if (!confirm("Отключить папку? Удалится только ссылка, ваши файлы останутся.")) return;
    await api(`/api/tasks/${t.id}/data/unbind`, { method: "POST" }); viewTask(t.id, "settings");
  };
}

async function bindDataPrompt(taskId, ide) {
  const path = prompt("Путь к папке с датасетом (станет data/, без копирования)");
  if (!path) return;
  try { await api(`/api/tasks/${taskId}/data/bind`, { method: "POST", json: { path } }); toast("папка подключена как data/"); ide.refreshTree(); }
  catch (e) { toast(e.message, true); }
}

// ---------------- Журнал ----------------
const JSTATUS = { active: "warn", checking: "warn", abandoned: "err", passed: "ok", partial: "warn", failed: "err" };

// Таблица попыток и «работы над ошибками» (стр. 23). opts.task_id — только одна задача.
const JF = [["", "все", () => true], ["library", "библиотека", r => r.mode === "library"], ["scratch", "с нуля", r => r.mode === "scratch"],
  ["abandoned", "брошенные", r => r.status === "abandoned"], ["errors", "с ошибками", r => ["abandoned", "partial", "failed"].includes(r.status)],
  ["reviews", "работа над ошибками", r => r.type === "review"]];
async function journalTable(box, opts = {}, filter = "") {
  const all = await api(`/api/journal?${new URLSearchParams(opts.task_id ? { task_id: opts.task_id } : {})}`);
  const pass = (JF.find(f => f[0] === filter) || JF[0])[2], rows = all.filter(pass);
  box.innerHTML = `<div class="row jr-filters">${JF.map(([k, n, f]) => { const c = all.filter(f).length;
      return `<button class="fchip ${k === filter ? "sel" : ""}" data-f="${k}" ${c || !k ? "" : "disabled"}>${n} <span class="faint">${c}</span></button>`; }).join("")}</div>
    ${rows.length ? `<div class="scroll-x"><table class="jr-table"><thead><tr><th>Дата</th>${opts.task_id ? "" : "<th>Задача</th>"}<th>Режим</th><th>Тип</th><th>Статус</th><th>Оценка</th><th>Время</th><th>«Проверить»</th><th>Эталон</th><th>Что пошло не так</th><th></th></tr></thead><tbody>
    ${rows.map(r => `<tr class="link" data-open="${r.type === "review" ? `#/review/${r.id}${r.status === "active" ? "" : "/report"}` : `#/attempt/${r.id}`}">
      <td class="nowrap muted">${fmtDate(r.date)}</td>${opts.task_id ? "" : `<td><span class="title">${esc(r.task)}</span></td>`}
      <td>${r.mode ? modeBadge(r.mode, { short: true }) : ""}</td>
      <td class="nowrap">${r.type === "review" ? `работа над ошибками${r.status === "active" ? ` <span class="faint small">шаг ${r.step}/3</span>` : ""}` : "попытка"}</td>
      <td><span class="badge dot ${JSTATUS[r.status] || ""}">${esc(r.status_name)}</span></td>
      <td class="mono-num">${r.score ?? '<span class="faint">—</span>'}</td><td class="mono muted">${fmtMs(r.total_ms)}</td>
      <td class="muted">${r.checks}</td><td>${r.ref_opened ? `<span class="warn small">${r.type === "review" ? "подглядывал" : "да"}</span>` : '<span class="faint">нет</span>'}</td>
      <td class="jr-why">${r.reason ? esc(r.reason) : '<span class="faint">—</span>'}</td>
      <td style="text-align:right">${r.type === "attempt" && ["abandoned", "partial", "passed"].includes(r.status)
        ? `<button class="small ${r.status === "passed" ? "link" : ""}" data-review="${r.id}">Работа над ошибками</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>` : emptyState({ icon: "files", title: "Записей нет", text: filter ? "По этому фильтру пусто." : "Сданные, брошенные попытки и работа над ошибками появятся здесь." })}`;
  $$("[data-f]", box).forEach(b => b.onclick = () => journalTable(box, opts, b.dataset.f));
  $$("tr[data-open]", box).forEach(tr => tr.onclick = e => { if (!e.target.closest("button")) location.hash = tr.dataset.open; });
  $$("[data-review]", box).forEach(b => b.onclick = e => { e.stopPropagation(); startReview(+b.dataset.review); });
  return rows;
}

async function viewJournal() {
  view.innerHTML = '<div class="journal-page"><div class="page-head"><h1>Журнал</h1><div class="muted">Все попытки и работа над ошибками, новые сверху</div></div><div class="card jr-card" id="jr"></div></div>';
  await journalTable($("#jr"));
}

// Начать «работу над ошибками»: если файлов «пишу сам» несколько — выбрать один или все подряд
async function startReview(attemptId) {
  const a = await api(`/api/attempts/${attemptId}`);
  const written = a.files.filter(f => a.roles[f] !== "given");
  let files = null;
  if (written.length > 1) {
    const choice = prompt(`Какой файл переписать? Введите имя (${written.join(", ")}) или «все», чтобы пройти все подряд.`, "все");
    if (choice === null) return;
    files = choice.trim().toLowerCase() === "все" ? null : [choice.trim()];
    if (files && !written.includes(files[0])) return toast("нет такого файла «пишу сам»", true);
  }
  try {
    const r = await api(`/api/attempts/${attemptId}/reviews`, { method: "POST", json: { files } });
    location.hash = `#/review/${r.id}`;
  } catch (e) { toast(e.message, true); }
}

// «1-я — 2/7, 2-я — 5/7, 3-я — 7/7»: сколько тестов прошло на шаге 3 в каждой работе над ошибками
const RV_STATUS = { passed: ["ok", "пройдена"], failed: ["err", "не пройдена"], abandoned: ["muted", "брошена"] };
function reviewsProgressHtml(list) {
  if (!list.length) return "";
  const rows = [...list].sort((x, y) => x.id - y.id).map((r, i) => {
    const st = r.status === "active" ? ["warn", `шаг ${r.step}/3`] : RV_STATUS[r.status] || ["muted", r.status];
    return `<div class="small"><a href="#/review/${r.id}/report">${i + 1}-я</a> — <b>${r.result || "—"}</b>
      <span class="${st[0]}">${st[1]}</span>${r.reason ? ` <span class="muted">· ${esc(r.reason)}</span>` : ""}</div>`;
  });
  return `<div class="label mt">Работа над ошибками</div>${rows.join("")}`;
}

// ---------------- Отчёт после сдачи (стр. 19) — отдельная страница; код и тесты — «Код в редакторе» ----------------
async function reportPage(a) {
  const rep = a.report, sc = rep.score ?? 0, hist = arr(rep.history);
  const prev = hist.length > 1 ? hist[hist.length - 2] : null;
  const [today, refs] = await Promise.all([api("/api/today").catch(() => null), api(`/api/attempts/${a.id}/reference`, { method: "POST" }).catch(() => ({ files: {} }))]);
  const next = today && [...today.overdue, ...today.due, ...today.new].find(x => x.id !== a.task_id);
  const brickOf = Object.fromEntries((a.bricks || []).filter(b => b.module).map(b => [b.module, b]));
  // по узлам: свои кирпичики и сама задача — режим и тесты из итогового прогона
  const tests = arr(rep.result?.tests);
  const nodes = [...(a.bricks || []).filter(b => b.source?.startsWith("self_")).map(b => ({ name: b.name, mode: b.mode, list: tests.filter(t => t.brick === b.name) })),
    { name: a.title, mode: a.mode, list: tests.filter(t => !t.brick) }];
  const written = a.files.filter(f => a.roles[f] !== "given" && (refs.files || {})[f] != null);
  const ring = (v, cls) => { const r = 54, c = 2 * Math.PI * r; return `<svg viewBox="0 0 128 128" class="ring"><circle cx="64" cy="64" r="${r}" class="rbg"/><circle cx="64" cy="64" r="${r}" class="rfg ${cls}" stroke-dasharray="${c * v / 100} ${c}"/></svg>`; };
  const cls = sc >= 70 ? "ok" : sc >= 50 ? "warn" : "err";
  const dueIn = a.due_at ? Math.round((Date.parse(a.due_at) - Date.now()) / 864e5) : null;
  const dt = prev?.total_ms != null ? prev.total_ms - a.total_ms : null;
  view.innerHTML = `<div class="report-page">
    <div class="row page-head"><div><div class="muted">${a.outcome === "passed" ? "Сдано" : "Сдано частично"} ${fmtDate(a.finished_at)}${hist.length ? ` · попытка ${hist.length}` : ""}</div>
      <div class="row"><h1 style="margin:0">${esc(a.title)}</h1>${modeBadge(a.mode)}</div></div><span class="grow"></span>
      <a class="btn link" href="#/attempt/${a.id}/code">Код в редакторе</a>
      ${next ? `<button id="rp-next">Следующая — ${esc(next.name || next.title)}</button>` : ""}
      ${a.status !== "checking" ? `<button class="primary" id="rp-work">Работа над ошибками</button>` : ""}</div>
    <div class="rp-top">
      <div class="card rp-score"><div class="ring-box">${ring(sc, cls)}<div class="ring-n"><b>${rep.score ?? "—"}</b><span class="faint small">из 100</span></div></div>
        <div><div class="row"><h2 style="margin:0">${esc(a.grade_name || "без уровня")}</h2><span class="muted">${a.due_at ? `следующее повторение${dueIn != null && dueIn > 0 ? ` через ${dueIn} ${plural(dueIn, "день", "дня", "дней")}` : ""} — ${fmtDay(a.due_at)}` : ""}</span></div>
          <div class="row mt">${Object.entries(a.grades).map(([g, n]) => `<button class="small ${+g === a.grade ? "sel" : "ghost"}" data-g="${g}">${n}${+g === a.grade && !a.grade_manual ? " · по оценке" : ""}</button>`).join("")}
            ${a.grade_manual ? '<button class="small link" data-g="">вернуть авто</button>' : ""}</div>
          <p class="muted small">Не согласен с оценкой — выбери уровень сам. Интервал пересчитается.</p>
          ${(rep.reasons || []).length ? `<p class="faint small">${rep.reasons.map(esc).join(" · ")}</p>` : ""}</div></div>
      <div class="card rp-nodes"><div class="label">По узлам</div>${nodes.map(n => {
        const ok = n.list.filter(t => t.status === "pass").length, tot = n.list.length;
        return `<div class="rp-node"><i class="sq ${n.mode === "library" ? "m-library" : "m-scratch"}"></i><b class="mono">${esc(n.name)}</b><span class="faint small">${MODE_NAME[n.mode] || ""}</span><span class="grow"></span>
          <span class="score-b ${tot && ok === tot ? "ok" : "err"}">тесты ${ok}/${tot}</span></div>`; }).join("")}</div>
    </div>
    <div class="rp-tiles">
      <div class="card"><div class="muted">Время</div><div class="big-n">${fmtMs(a.total_ms)}</div>${dt != null && Math.abs(dt) > 1000 ? `<div class="${dt > 0 ? "ok" : "warn"} small">на ${fmtMs(Math.abs(dt))} ${dt > 0 ? "быстрее" : "дольше"} прошлой</div>` : ""}</div>
      <div class="card"><div class="muted">«Проверить»</div><div class="big-n">${a.checks} ${plural(a.checks, "раз", "раза", "раз")}</div></div>
      <div class="card"><div class="muted">Эталон</div><div class="big-n">${a.ref_opened ? "открывал" : "не открывал"}</div><div class="faint small">${a.ref_opened ? "штраф за подсмотр" : "штрафа нет"}</div></div>
      <div class="card"><div class="muted">Оценка по попыткам</div><div id="rp-h1"></div></div>
      <div class="card"><div class="muted">Время по попыткам</div><div id="rp-h2"></div></div>
    </div>
    ${(rep.warnings || []).length ? `<div class="card"><ul class="plain">${rep.warnings.map(x => `<li class="${x.level}">${esc(x.text)}</li>`).join("")}</ul></div>` : ""}
    ${written.map((f, i) => `<div class="card rp-diff"><div class="rp-dh"><b>${esc(f)}</b><span class="muted small" id="rp-sum-${i}"></span><span class="grow"></span></div><div class="rp-dv" id="rp-d-${i}"></div></div>`).join("")}
    ${rep.judge && rep.judge !== "pending" && rep.judge.ok ? `<div class="card"><div class="row"><i class="t-dot fail"></i><b>${esc(rep.judge.comment)}</b></div>
      ${rep.judge.differences.length ? `<ul class="plain">${rep.judge.differences.map(d => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}<div class="faint small">${esc(rep.judge.provider)} · ${esc(rep.judge.model)} · на оценку не влияет</div></div>`
      : rep.judge === "pending" ? '<div class="card muted spinner small">комментарий модели готовится</div>' : ""}
    ${reviewsProgressHtml(a.reviews || [])}
  </div>`;
  const spark = (el, vals, fmt) => {
    if (!vals.length) return;
    const W = 220, H = 60, max = Math.max(...vals), min = Math.min(...vals), y = v => H - 8 - (max === min ? .5 : (v - min) / (max - min)) * (H - 16);
    const x = i => vals.length === 1 ? W / 2 : 8 + i * (W - 16) / (vals.length - 1);
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H + 16}" class="spark"><path d="${vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("")}"/>${vals.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="3"/><text x="${x(i)}" y="${H + 12}" text-anchor="middle">${fmt(v)}</text>`).join("")}</svg>`;
  };
  spark($("#rp-h1"), hist.slice(-5).map(h => h.score ?? 0), v => v);
  spark($("#rp-h2"), hist.slice(-5).map(h => h.total_ms || 0), v => fmtMs(v));
  current = { dispose: () => { (current?._diffs || []).forEach(d => d.dispose?.()); } };
  const diffs = [];
  current._diffs = diffs;
  for (const [i, f] of written.entries()) {
    const box = $(`#rp-d-${i}`);
    const mine = (await api(`/api/attempts/${a.id}/file?path=${encodeURIComponent(f)}`).catch(() => ({ content: "" }))).content;
    diffs.push(await diffSwitcher(box, mine, refs.files[f], ["эталон", "мой код"]));
  }
  $$("[data-g]").forEach(b => b.onclick = async () => {
    const na = await api(`/api/attempts/${a.id}/grade`, { method: "POST", json: { grade: b.dataset.g ? +b.dataset.g : null } });
    toast(`уровень: ${na.grade_name} · повтор ${na.due_at}`); reportPage(na);
  });
  const nx = $("#rp-next");
  if (nx) nx.onclick = () => startAttempt(next.id, next.mode);
  const wk = $("#rp-work");
  if (wk) wk.onclick = () => startReview(a.id);
  if (rep.judge === "pending") setTimeout(async () => { if ($(".report-page")) reportPage(await api(`/api/attempts/${a.id}`)); }, 3000);
}

// ---------------- Решение (IDE) ----------------
const OUTCOME_TITLE = { abandoned: "брошена", passed: "сдана", partial: "тесты частично", checking: "проверяется" };

async function viewAttempt(id, sub) {
  let a = await api(`/api/attempts/${id}`);
  const readonly = a.status !== "active";
  if (readonly && a.report?.weights && sub !== "code") return reportPage(a);  // сданная — страница отчёта
  const base = `/api/attempts/${id}`;
  const loadedAt = Date.now(), baseMs = a.total_ms;
  const totalMs = () => readonly ? a.total_ms : baseMs + (Date.now() - loadedAt);
  const written = a.files.filter(f => a.roles[f] !== "given");  // свои файлы «пишу сам» и кирпичики bricks/…
  const brickOf = Object.fromEntries((a.bricks || []).filter(b => b.module).map(b => [b.module, b]));
  let refFiles = null;
  if (readonly) refFiles = (await api(`${base}/reference`, { method: "POST" })).files;  // после окончания — без штрафа
  const needsWork = readonly && (a.outcome === "abandoned" || a.outcome === "partial");
  // шапка: тема (крошки), уровень, режим; «попытка N · лучшее X» — из списка попыток
  const [tk, topics, tries] = await Promise.all([api(`/api/tasks/${a.task_id}`).catch(() => null), apiList("/api/topics"), apiList(`/api/tasks/${a.task_id}/attempts`)]);
  const level = taskLevel(tk);
  const nTry = tries.length - tries.findIndex(x => x.id === a.id), best = Math.max(-1, ...tries.filter(x => x.score != null).map(x => x.score));
  const fileMode = p => brickOf[p] ? (brickOf[p].mode || (brickOf[p].source === "self_library" ? "library" : "scratch")) : a.files.includes(p) && a.roles[p] !== "given" ? a.mode : null;
  const bricksNote = (() => {
    const other = (a.bricks || []).filter(b => b.source?.startsWith("self_") && fileMode(b.module) !== a.mode);
    return other.length ? `<span class="faint">+ ${other.map(b => esc(b.name)).join(", ")} — ${MODE_NAME[fileMode(other[0].module)] === "библиотека" ? "библиотекой" : "с нуля"}</span>` : "";
  })();

  const leftTabs = [
    { id: "desc", label: "Описание", render: el => { el.innerHTML = `<h2 class="ide-h">${esc(a.title)}</h2>
      <div class="md">${a.description ? md(a.description) : '<p class="muted">описания нет</p>'}</div>
      <div class="label mt">Что пишешь и как</div>
      <div class="wlist">${a.files.filter(f => a.roles[f] !== "given").map(f => { const m = fileMode(f);
        return `<div class="wrow"><span class="fsq-l ${m ? `m-${m}` : ""}"></span><span class="mono wname">${esc(f)}</span><span class="grow"></span>${m ? `<span class="mi mi-${m === "library" ? "lib" : "scr"}" title="${MODE_TITLE[m]}">${ICON[MODE_ICON[m]]}</span>` : ""}</div>`; }).join("")}</div>
      ${a.files.some(f => a.roles[f] === "given") ? `<div class="faint small mt">даны готовыми: ${a.files.filter(f => a.roles[f] === "given").map(f => `<span class="mono">${esc(f)}</span>`).join(", ")}</div>` : ""}
      <div class="faint small mt">v${a.version} · лимит ${a.timeout} с</div>`; } },
    ...(readonly ? [{ id: "report", label: a.report?.weights ? "Отчёт" : "Итог", render: el => a.report?.weights ? renderReport(el, a, na => { a = na; }) : renderAbandoned(el, a) }] : []),
    { id: "attempts", label: `Попытки${tries.length ? ` <span class="faint">${tries.length}</span>` : ""}`, html: true, render: async el => {
      const list = await api(`/api/tasks/${a.task_id}/attempts`);
      const done = list.filter(x => x.score != null).reverse();
      el.innerHTML = `${list.map(x => `<div class="row small" style="padding:4px 0;border-bottom:1px solid var(--line)"><a href="#/attempt/${x.id}">${fmtDate(x.date)}</a>
          <span class="badge ${JSTATUS[x.status] || ""}">${esc(x.status_name)}</span><span class="grow"></span>${x.score != null ? `<b>${x.score}</b>` : ""}<span class="mono muted">${fmtMs(x.total_ms)}</span></div>`).join("")}
        ${done.length ? '<div id="h" class="mt"></div>' : ""}`;
      if (done.length) historyCharts($("#h", el), done.map(x => ({ date: x.finished_at, score: x.score, total_ms: x.total_ms })));
    } },
    ...(readonly ? [] : [{ id: "ref", label: `${ICON.lock}Эталон`, html: true, render: el => renderReference(el, a, base, readonly, () => refFiles, f => { refFiles = f; a.ref_opened = true; }) }]),
    ...((a.bricks || []).length ? [{ id: "asm", label: "Сборка", render: el => renderAssemblyTab(el, a) }] : []),
  ];

  current = await openIDE(view, {
    title: `${a.title} · ${MODE_NAME[a.mode] || a.mode}` + (readonly ? ` · ${OUTCOME_TITLE[a.outcome] || a.outcome}` : ""), base, readonly, back: `#/task/${a.task_id}`,
    heading: a.title, crumbs: tk?.topic_id ? esc(topicPath(topics, tk.topic_id)).replaceAll(" / ", '<span class="sep">/</span>') : "",
    badges: `${levelTag(level)}${modeBadge(a.mode)}${bricksNote}`,
    meta: tries.length ? `попытка ${nTry}${best >= 0 ? ` · лучшее ${best}` : ""}` : "",
    fileMode, python: a.python, checks: a.checks, hiddenTests: true, taskTitle: a.title,
    rule: `${modeBadge(a.mode, { short: true })} ${a.mode === "library" ? "через готовую функцию библиотеки — её вызов проверяется" : "своими руками — готовая функция библиотеки запрещена"}`,
    roles: a.roles, main: a.main_file, pyFiles: a.files, preload: a.files, expand: [],
    open: readonly ? written : [a.main_file, ...written.filter(f => f !== a.main_file)].filter(Boolean),
    tabNote: p => brickOf[p] ? `<span class="role" title="${esc(brickOf[p].title)}">кирпичик</span>` : "",
    refFiles: readonly ? refFiles : null, cmpMode: "diff", dataLink: a.data_link, initialOutput: a.last_output,
    leftTabs, leftTab: readonly ? "report" : "desc",
    run: path => api(`${base}/run`, { method: "POST", json: { path } }).then(r => r.job),
    exec: code => api(`${base}/exec`, { method: "POST", json: { code } }).then(r => r.job),
    stop: () => api(`${base}/stop`, { method: "POST" }),
    check: () => api(`${base}/check`, { method: "POST" }).then(r => { a.checks = r.checks; updateChecks(); return r.job; }),
    bindData: ide => bindDataPrompt(a.task_id, ide),
    buttons: (el, ide, sub, menu) => {
      el.innerHTML = `<span class="timer" id="timer" title="время попытки">${ICON.clock}${fmtMs(totalMs())}</span>
        ${readonly ? `<span class="badge ${JSTATUS[a.outcome] || ""}">${OUTCOME_TITLE[a.outcome] || a.outcome}</span>${a.score != null ? `<b>${a.score}</b>` : ""}
            ${a.status !== "checking" ? `<button class="${needsWork ? "primary" : "ghost"}" id="work">${needsWork ? "Работа над ошибками сейчас" : "Работа над ошибками"}</button>` : ""}`
          : ""}`;
      if (!readonly) menu.innerHTML = `<div class="menu-row faint" id="checks"></div><button class="menu-item" id="reset">↺ Вернуть текущий файл к заготовке</button>
             <button class="menu-item danger" id="abandon" title="попытка сохранится как брошенная">Сбросить попытку</button>`;
      if (!readonly) sub.innerHTML = `<button class="primary" id="submit">${ICON.arrowUp}Сдать</button>`;
      if (readonly) {
        const w = $("#work", el);
        if (w) w.onclick = () => startReview(a.id);
        return;
      }
      $("#reset", menu).onclick = async () => {
        const p = ide.current;
        if (!p || !a.files.includes(p)) return toast("откройте файл задачи", true);
        if (!confirm(`Вернуть ${p} к заготовке? Текущий код этого файла пропадёт.`)) return;
        const r = await api(`${base}/reset`, { method: "POST", json: { path: p } });
        ide.models[p].setValue(r.content);
        await ide.save(p);
      };
      $("#abandon", menu).onclick = async () => {
        if (!confirm("Сбросить попытку? Она сохранится в истории как брошенная (со всем кодом), в повторениях — как «забыл».")) return;
        await finishAs("abandon");
        viewAttemptAgain();
      };
      $("#submit", sub).onclick = async () => {
        if (!confirm("Сдать решение? Будет финальный прогон тестов и оценка.")) return;
        await ide.saveAll();
        ended = true;
        clearInterval(tick); clearInterval(autosave);
        $("#submit", sub).disabled = true;
        ide.showConsole("tests");
        const tv = $('[data-cv="tests"]', view);
        tv.innerHTML = '<div class="run-head"><span>финальный прогон</span><span class="spinner"></span></div><div data-o></div>';
        const { job } = await api(`${base}/submit`, { method: "POST", json: { total_ms: totalMs() } });
        await followJob(job, outs => renderOutputs($("[data-o]", tv), outs, ide.rawUrl));
        viewAttemptAgain();
      };
    },
  });
  const ide = current;
  let ended = readonly;
  function updateChecks() { const c = $("#checks"); if (c) c.textContent = a.checks ? `«Проверить»: ${a.checks}` : ""; }
  updateChecks();
  if (readonly) ide.showTests(a.report?.result || a.last_check);
  const saveTime = () => ended ? null : fetch(`${base}/time`, { method: "PUT", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ total_ms: Math.round(totalMs()) }) }).catch(() => {});
  // Уход без сдачи = «брошена»: код всех файлов и время сохраняются
  async function finishAs() {
    if (ended) return;
    ended = true;
    await ide.saveAll();
    await api(`${base}/abandon`, { method: "POST", json: { total_ms: Math.round(totalMs()) } });
  }
  function viewAttemptAgain() { ide.leaveGuard = null; ide.dispose(); current = null; viewAttempt(id); }
  const onPageHide = () => {
    if (ended) return;
    ended = true;
    navigator.sendBeacon(`${base}/abandon`, new Blob([JSON.stringify({ total_ms: Math.round(totalMs()) })], { type: "application/json" }));
  };
  const onBeforeUnload = e => { if (!ended) { ide.saveAll(); e.preventDefault(); e.returnValue = ""; } };
  if (!readonly) {
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("beforeunload", onBeforeUnload);
    ide.leaveGuard = () => {
      if (ended) return true;
      if (!confirm("Уйти без сдачи? Попытка сохранится как брошенная (с кодом и временем).")) return false;
      finishAs();
      return true;
    };
  }
  const tick = setInterval(() => { const t = $("#timer"); if (!t) return clearInterval(tick); t.textContent = fmtMs(totalMs()); }, 1000);
  const autosave = readonly ? null : setInterval(saveTime, 15000);
  const dispose = ide.dispose;
  ide.dispose = () => {
    clearInterval(tick); clearInterval(autosave);
    window.removeEventListener("pagehide", onPageHide);
    window.removeEventListener("beforeunload", onBeforeUnload);
    dispose();
  };
}

function renderAbandoned(el, a) {
  const ch = a.last_check;
  el.innerHTML = `<div class="row"><span class="badge err">брошена</span><span class="muted small">${fmtDate(a.finished_at)}</span></div>
    <p>Время: <b class="mono">${fmtMs(a.total_ms)}</b> · «Проверить»: ${a.checks}${a.ref_opened ? " · эталон открывал" : ""}</p>
    <p class="muted small">В повторениях — как «забыл». Следующее повторение: <b>${a.due_at || "—"}</b>.</p>
    <p class="small">${ch ? `Последняя проверка: <b class="${ch.passed === ch.total && ch.total ? "ok" : "err"}">${ch.passed}/${ch.total}</b> тестов` : "Тесты в этой попытке не запускались."}
      ${a.last_output ? ` · последний запуск: <span class="mono">${esc(a.last_output.path)}</span>` : ""}</p>
    <p class="muted small">Код файлов — каким вы его оставили — во вкладках редактора: переключатель «мой код / эталон / diff».</p>
    ${reviewsProgressHtml(a.reviews)}
    <button class="primary mt" id="work2">Работа над ошибками сейчас</button>`;
  $("#work2", el).onclick = () => startReview(a.id);
}

function renderReference(el, a, base, readonly, get, set) {
  const show = files => {
    el.innerHTML = Object.entries(files).map(([f, code]) => `<div class="label mt">${esc(f)}${a.roles[f] === "given" ? " · дан" : ""}</div><pre class="md" data-code="${esc(f)}" style="margin:0"><code>${esc(code)}</code></pre>`).join("");
    if (window.monaco) $$("[data-code]", el).forEach(p => monaco.editor.colorize(files[p.dataset.code], "python", {}).then(h => { p.innerHTML = `<code>${h}</code>`; }));
  };
  if (get()) return show(get());
  if (readonly || a.ref_opened) {
    return api(`${base}/reference`, { method: "POST" }).then(r => { set(r.files); show(r.files); });
  }
  el.innerHTML = `<p>Эталон скрыт до сдачи.</p><p class="muted small">Если открыть его сейчас, оценка снизится, а уровень повторения понизится на один.</p>
    <button id="ref-open" class="danger">Показать эталон</button>`;
  $("#ref-open", el).onclick = async () => {
    if (!confirm("Открыть эталон? Оценка этой попытки снизится.")) return;
    const r = await api(`${base}/reference`, { method: "POST" });
    set(r.files); show(r.files);
  };
}

function renderReport(el, a, update) {
  const rep = a.report, w = rep.weights || {};
  const sc = rep.score;
  el.innerHTML = `
    <div class="row"><span class="score ${sc >= 70 ? "ok" : sc >= 50 ? "warn" : "err"}">${sc ?? "—"}</span><span class="muted">/ 100</span><span class="grow"></span>
      <span class="badge ${GRADE_CLS[a.grade_name] || ""}">${a.grade_name || "без уровня"}${a.grade_manual ? " · вручную" : ""}</span></div>
    <div class="muted small mt">${(rep.reasons || []).map(esc).join(" · ")}</div>
    <div class="small mt">Следующее повторение: <b>${a.due_at || "—"}</b></div>
    <div class="row mt"><span class="muted small">Не согласен с оценкой:</span>${Object.entries(a.grades).map(([g, n]) => `<button class="small ${+g === a.grade ? "sel" : ""}" data-g="${g}">${n}</button>`).join("")}
      ${a.grade_manual ? '<button class="small ghost" data-g="">авто</button>' : ""}</div>
    <ul class="plain mt">${(rep.warnings || []).map(x => `<li class="${x.level}">${esc(x.text)}</li>`).join("")}</ul>
    ${reviewsProgressHtml(a.reviews || [])}
    <details class="mt"><summary class="muted small">как посчитана оценка</summary><div class="formula mt">${esc((rep.parts || []).join("\n") || "—")}
оценка = 100 · прошедшие / учтённые тесты (сломанные на эталоне не учитываются)
  − ${w.check_penalty} за каждое «Проверить» сверх ${w.free_checks} (не больше ${w.check_penalty_max})
  − ${w.ref_penalty}, если эталон открыт до сдачи
  − ${w.time_penalty}, если время дольше прошлой попытки больше чем на ${w.slower_pct}%
уровень: ≥90 легко · ≥70 нормально · ≥50 трудно · иначе забыл; открытый эталон −1 уровень
веса — в настройках</div></details>
    ${rep.judge ? `<div class="label mt">Комментарий LLM</div>${rep.judge === "pending" ? '<div class="muted spinner small">модель думает</div>'
      : rep.judge.ok ? `<p>${esc(rep.judge.comment)}</p>${rep.judge.differences.length ? `<ul class="plain">${rep.judge.differences.map(d => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}<div class="muted small">${esc(rep.judge.provider)} · ${esc(rep.judge.model)} · на оценку не влияет</div>`
      : `<p class="warn small">LLM недоступна: ${esc(rep.judge.error)}</p>`}` : ""}
    <div class="label mt">Оценка и время по попыткам</div><div id="h"></div>
    <p class="muted small mt">Код рядом с эталоном — во вкладках редактора (diff), результаты тестов — во вкладке «Тесты» внизу.</p>`;
  historyCharts($("#h", el), rep.history || []);
  $$("[data-g]", el).forEach(b => b.onclick = async () => {
    const na = await api(`/api/attempts/${a.id}/grade`, { method: "POST", json: { grade: b.dataset.g ? +b.dataset.g : null } });
    update(na); toast(`уровень: ${na.grade_name} · повтор ${na.due_at}`); renderReport(el, na, update);
  });
  if (rep.judge === "pending") setTimeout(async () => {
    if (!document.body.contains(el)) return;
    const na = await api(`/api/attempts/${a.id}`); update(na); renderReport(el, na, update);
  }, 3000);
}

// ---------------- Работа над ошибками ----------------
const RSTEPS = [[1, "Смотрю"], [2, "Переписываю с подглядыванием"], [3, "По памяти"]];
function stepperHtml(r) {
  return `<div class="stepper">${RSTEPS.map(([n, name]) => `<span class="st ${r.status === "active" && r.step === n ? "cur" : (r.status === "passed" || r.step > n) ? "done" : ""}"><i>${r.status === "passed" || r.step > n ? "✓" : n}</i>${name}</span>`).join('<span class="st-line"></span>')}
    ${r.files.length > 1 ? `<span class="muted small">файл ${r.idx + 1} из ${r.files.length}: <span class="mono">${esc(r.file)}</span></span>` : `<span class="muted small mono">${esc(r.file)}</span>`}</div>`;
}

async function viewReview(id, sub) {
  if (sub === "report") return reviewReport(id);
  const r = await api(`/api/reviews/${id}`);
  const base = `/api/reviews/${id}`;
  if (r.status !== "active") return reviewReport(r.id);
  if (r.step === 1) return reviewStep1(r);

  // Шаги 2–3: та же IDE, что в решении (файлы, data/, консоль, вывод)
  const step2 = r.step === 2;
  const refTab = { id: "ref", label: "Эталон", render: el => {
    el.style.padding = "0";
    el.innerHTML = `<div class="small muted row" style="padding:8px 12px;border-bottom:1px solid var(--line)">эталон <span class="mono">${esc(r.file)}</span> — только чтение<span class="grow"></span><span id="sim-pct"></span></div><div id="ref-ed" style="height:calc(100% - 36px)"></div>`;
    const ed = monaco.editor.create($("#ref-ed", el), { value: r.reference, language: "python", readOnly: true, automaticLayout: true,
      minimap: { enabled: false }, fontFamily: "JetBrains Mono, Menlo, monospace", fontSize: 13, fontLigatures: false, scrollBeyondLastLine: false });
    const prevDispose = el._dispose;
    el._dispose = () => { ed.dispose(); prevDispose && prevDispose(); };
  } };
  let showingRef = false;
  const taskTab = { id: "task", label: "Задание", render: el => {
    el.innerHTML = `<p>Напишите <span class="mono">${esc(r.file)}</span> заново по памяти и сдайте тестами («Сдать шаг»).
        Если тесты пройдут без подглядывания — шаг пройден и задача вернётся на повтор завтра.</p>
      ${r.peeked ? `<p class="warn small">Эталон подсмотрен (${r.peeks || 1} раз) — этот шаг не засчитается.</p>` : ""}
      ${showingRef ? `<button class="ghost small" id="hide-ref">Скрыть эталон</button><pre class="md"><code>${esc(r.reference || "")}</code></pre>`
        : `<button class="danger" id="peek">${r.peeked ? "Подсмотреть ещё раз" : "Подсмотреть эталон"}</button><p class="muted small">Каждое подглядывание отмечается: шаг тогда не засчитывается.</p>`}
      <div class="md mt">${r.description ? md(r.description) : ""}</div>`;
    const pk = $("#peek", el), hd = $("#hide-ref", el);
    if (hd) hd.onclick = () => { showingRef = false; taskTab.render(el); };
    if (pk) pk.onclick = async () => {
      if (!r.peeked && !confirm("Подсмотреть эталон? Шаг 3 тогда не засчитается.")) return;
      const nr = await api(`${base}/peek`, { method: "POST" });
      Object.assign(r, nr); showingRef = true; taskTab.render(el);
    };
  } };
  let decorations = [], hlTimer = null, hlSeq = 0;
  // зелёный — строка совпала с эталоном по смыслу, жёлтый — отличается (пробелы и комментарии не в счёт)
  const highlight = (model, editor) => {
    clearTimeout(hlTimer);
    hlTimer = setTimeout(async () => {
      const seq = ++hlSeq, text = model.getValue();
      const cmp = await compareCode(text, r.reference || "").catch(() => null);
      if (!cmp || seq !== hlSeq || model.isDisposed()) return;
      const lines = text.split("\n");
      const mark = (n, same) => ({ range: new monaco.Range(n, 1, n, 1), options: { isWholeLine: true, className: same ? "line-same" : "line-diff",
        linesDecorationsClassName: same ? "glyph-same" : "glyph-diff" } });
      const dec = [...cmp.mine.same.filter(n => lines[n - 1]?.trim()).map(n => mark(n, true)),
                   ...cmp.mine.changed.filter(n => lines[n - 1]?.trim()).map(n => mark(n, false))];
      decorations = editor.deltaDecorations(decorations, dec);
      const pct = $("#sim-pct");
      if (pct) pct.innerHTML = text.trim() ? `совпадение по смыслу: <b class="${cmp.equal ? "ok" : ""}">${cmp.similarity}%</b>` : "";
    }, 250);
  };
  const t0 = Date.now(), started = new Date(r.step_started).getTime();
  current = await openIDE(view, {
    title: `${r.title} · ${MODE_NAME[r.mode] || ""} · работа над ошибками`, base, back: `#/attempt/${r.attempt_id}`,
    open: [r.file], preload: r.all_files, pyFiles: r.all_files, expand: [], main: r.file, dataLink: r.data_link,
    tabNote: p => p === r.file ? '<span class="role">переписываю</span>' : '<span class="role">эталон</span>',
    readonlyFile: p => r.all_files.includes(p) && p !== r.file,
    noPaste: p => step2 && p === r.file,
    onOpen: (p, model, ide) => {
      if (!step2 || p !== r.file || model._hl) return;
      model._hl = true;
      highlight(model, ide.editor);
      model.onDidChangeContent(() => { if (ide.current === r.file) highlight(model, ide.editor); });
    },
    leftTabs: step2 ? [refTab, { id: "desc", label: "Описание", render: el => { el.innerHTML = `<div class="md">${md(r.description || "")}</div>`; } }] : [taskTab],
    leftTab: step2 ? "ref" : "task",
    checkLabel: step2 ? "✓ Проверить" : "Сдать шаг 3", checkClass: step2 ? "ghost" : "primary",
    checkTitle: step2 ? "шаг закроется, когда все тесты пройдут" : "финальная проверка шага 3 тестами",
    run: path => api(`${base}/run`, { method: "POST", json: { path } }).then(x => x.job),
    exec: code => api(`${base}/exec`, { method: "POST", json: { code } }).then(x => x.job),
    stop: () => api(`${base}/stop`, { method: "POST" }),
    check: () => api(`${base}/check`, { method: "POST" }).then(x => x.job),
    onCheck: (check, result) => {
      const o = result?.outcome;
      if (o === "step2_passed") { toast("тесты прошли — шаг 2 закрыт, теперь по памяти"); reopen(); }
      else if (o === "next_file") { toast("файл пройден — следующий"); reopen(); }
      else if (o === "passed" || o === "failed") reopen();
      else if (step2) toast(`прошло ${check?.passed ?? 0}/${check?.total ?? 0} — шаг закроется, когда пройдут все тесты`, true);
    },
    bindData: ide => bindDataPrompt(r.task_id, ide),
    buttons: el => {
      el.innerHTML = `${stepperHtml(r)}<span class="timer" id="timer" title="время шага">${fmtMs(Date.now() - started)}</span>
        <button class="ghost" id="r-abandon" title="закончить работу над ошибками">Бросить</button>`;
      $("#r-abandon", el).onclick = async () => {
        if (!confirm("Бросить работу над ошибками? Она останется в журнале как брошенная.")) return;
        await api(`${base}/abandon`, { method: "POST" }); reopen();
      };
    },
  });
  const ide = current;
  const tick = setInterval(() => { const tt = $("#timer"); if (!tt) return clearInterval(tick); tt.textContent = fmtMs(Date.now() - started); }, 1000);
  const dispose = ide.dispose;
  ide.dispose = () => { clearInterval(tick); const lb = $("#left-body"); lb && lb._dispose && lb._dispose(); dispose(); };
  function reopen() { ide.dispose(); current = null; viewReview(id); }
  void t0;
}

// Шаг 1: эталон открыт полностью, рядом мой код из попытки с подсветкой отличий
async function reviewStep1(r) {
  view.innerHTML = `<div class="row" style="margin-bottom:10px"><a href="#/attempt/${r.attempt_id}" class="muted">← попытка</a><span class="grow"></span>${stepperHtml(r)}</div>
    <div class="card"><div class="row"><h2 style="margin:0">${esc(r.title)} · смотрю</h2><span class="grow"></span>
      <button class="ghost" id="r-abandon">Бросить</button><button class="primary" id="next">Понял, дальше →</button></div>
      <p class="muted small">Слева — эталон, справа — ваш код из попытки. По умолчанию сравнение «по смыслу»: пробелы, пустые строки и комментарии не считаются отличием. Разберитесь, что пошло не так, затем перепишите с подглядыванием.</p>
      <div id="diff" style="height:calc(100vh - 270px);min-height:360px;border-radius:6px;overflow:hidden;background:var(--bg)"></div></div>`;
  const dv = await diffSwitcher($("#diff"), r.mine || "", r.reference || "", ["эталон", "мой код из попытки"]);
  current = { dispose: () => dv.dispose() };
  $("#next").onclick = async () => { await api(`/api/reviews/${r.id}/next`, { method: "POST" }); current.dispose(); current = null; viewReview(r.id); };
  $("#r-abandon").onclick = async () => {
    if (!confirm("Бросить работу над ошибками?")) return;
    await api(`/api/reviews/${r.id}/abandon`, { method: "POST" }); current.dispose(); current = null; viewReview(r.id);
  };
}

// Полный отчёт по работе над ошибками: по каждому файлу и шагу — время, подглядывания и история прогонов
// (код на момент прогона, тесты с traceback, вывод, diff с эталоном по смыслу)
async function reviewReport(id) {
  const r = await api(`/api/reviews/${id}/report`);
  const res = { passed: ["ok", "Пройдена: шаг 3 сдан тестами без подглядывания — повтор завтра"], failed: ["err", "Не пройдена — задача сегодня же снова в «Сегодня»"],
                abandoned: ["muted", "Брошена"], active: ["warn", "В процессе"] }[r.status] || ["muted", r.status];
  const total = r.log.reduce((t, x) => t + x.ms, 0);
  const lastLog = r.log[r.log.length - 1];
  let file = r.open_step?.file || lastLog?.file || r.files[0];
  let step = r.open_step?.step >= 2 ? r.open_step.step : lastLog && lastLog.step >= 2 ? lastLog.step : r.runs.some(x => x.step === 3) ? 3 : 2;
  let sel = null, sub = null, disp = [];
  const disposeAll = () => { disp.forEach(d => d.dispose()); disp = []; };
  current = { dispose: disposeAll };
  const unit = Object.keys(r.bricks || {}).length ? "файл / кирпичик" : "файл";
  const fname = f => r.bricks?.[f] ? `${f} · ${r.bricks[f]}` : f;
  view.innerHTML = `<div class="row" style="margin-bottom:10px"><a href="#/attempt/${r.attempt_id}" class="muted">← исходная попытка</a>
      ${r.status === "active" ? `<span class="grow"></span><a class="btn primary" href="#/review/${r.id}">Продолжить</a>` : ""}</div>
    <div class="card"><h2>${esc(r.title)} · работа над ошибками</h2>${stepperHtml(r)}
      <p class="${res[0]} mt"><b>${res[1]}</b>${r.reason ? ` <span class="small">— ${esc(r.reason)}</span>` : ""}</p>
      <p class="small">Следующее повторение: <b>${r.due_at || "—"}</b> · всего ${fmtMs(total)} · ${fmtDate(r.started_at)}${r.finished_at ? ` — ${fmtDate(r.finished_at)}` : ""}</p>
      ${r.details ? "" : '<p class="warn small">Детали не сохранялись: запись сделана до того, как приложение начало сохранять прогоны. Есть только сводка по шагам.</p>'}
      <details class="mt"${r.details ? "" : " open"}><summary class="muted small">сводка по шагам</summary>
      <table class="mt"><thead><tr><th>${unit}</th><th>Шаг</th><th>Время</th><th>«Проверить»</th><th>Итог</th></tr></thead><tbody>
        ${r.log.map(x => `<tr><td class="mono">${esc(x.file)}</td><td>${x.step} · ${RSTEPS[x.step - 1][1]}</td><td class="mono">${fmtMs(x.ms)}</td><td class="muted">${x.checks}</td>
          <td>${x.passed ? '<span class="ok">✓</span>' : '<span class="err">✗</span>'}${x.peeked ? ` <span class="warn small">подглядывал${x.peeks > 1 ? ` ×${x.peeks}` : ""}</span>` : ""}</td></tr>`).join("")}</tbody></table></details></div>
    ${r.details ? `<div class="card">
      ${r.files.length > 1 ? `<div class="row" id="rr-files" style="margin-bottom:8px"><span class="muted small">${unit}:</span>${r.files.map(f => `<button class="small" data-file="${esc(f)}">${esc(fname(f))}${r.log.some(x => x.file === f && !x.passed) ? ' <span class="err">✗</span>' : ""}</button>`).join("")}</div>` : ""}
      <div class="seg" id="rr-steps"><button data-step="2">Шаг 2 (с подглядыванием)</button><button data-step="3">Шаг 3 (по памяти)</button></div>
      <div id="rr-sum" class="small" style="margin:10px 0"></div>
      <div class="rr-grid"><div class="rr-runs" id="rr-runs"></div><div class="rr-detail" id="rr-detail"></div></div></div>` : ""}
    <div class="row"><a class="btn" href="#/task/${r.task_id}">К задаче</a><a class="btn" href="#/journal">Журнал</a></div>`;
  if (!r.details) return;
  await loadMonaco();
  const hhmm = iso => new Date(iso).toLocaleTimeString("ru-RU");
  const KIND = { check: x => x.step === 3 ? "Сдать шаг 3" : "Проверить", run: x => `Запустить ${x.path || ""}`, final: () => "итог шага" };

  function items() {
    const runs = r.runs.filter(x => x.file === file && x.step === step);
    const lg = r.log.find(x => x.file === file && x.step === step && "code" in x);
    const open = r.open_step && r.open_step.file === file && r.open_step.step === step ? r.open_step : null;
    const fin = lg || open;
    if (fin) {
      const lastCheck = [...runs].reverse().find(x => x.kind === "check");
      runs.push({ kind: "final", n: "итог", code: { [file]: fin.code }, check: lastCheck?.check, at: lg?.ended, open: !!open,
                  outputs: lastCheck?.outputs || [], similarity: fin.similarity });
    }
    return runs;
  }
  function render() {
    disposeAll();
    $$("[data-step]").forEach(b => b.classList.toggle("sel", +b.dataset.step === step));
    $$("[data-file]").forEach(b => b.classList.toggle("sel", b.dataset.file === file));
    const lg = r.log.find(x => x.file === file && x.step === step);
    const open = r.open_step && r.open_step.file === file && r.open_step.step === step ? r.open_step : null;
    const info = lg || open;
    $("#rr-sum").innerHTML = !info ? '<span class="muted">шаг не начинали</span>'
      : `время шага <b class="mono">${fmtMs(info.ms)}</b> · «${step === 3 ? "Сдать" : "Проверить"}»: ${info.checks} ·
         ${step === 2 ? '<span class="muted">эталон был рядом (так задумано)</span>' : info.peeked ? `<span class="warn">подглядывал в эталон: ${info.peeks || 1} раз</span>` : '<span class="ok">не подглядывал</span>'}
         ${lg ? ` · итог: ${lg.passed ? '<span class="ok">✓ пройден</span>' : '<span class="err">✗ не пройден</span>'}` : ' · <span class="warn">шаг не закончен</span>'}
         ${info.similarity != null ? ` · совпадение с эталоном по смыслу: <b>${info.similarity}%</b>` : ""}`;
    const list = items();
    $("#rr-runs").innerHTML = list.length ? list.map((x, i) => {
      const c = x.check, ok = c && c.total && c.passed === c.total;
      const resTxt = c ? `<b class="${ok ? "ok" : "err"}">${c.total ? `${c.passed}/${c.total}` : "ошибка"}</b>`
        : x.kind === "run" ? `<span class="${x.result?.status === "ok" ? "ok" : "err"} small">${x.result?.status === "ok" ? "ок" : esc(x.result?.status || "—")}</span>` : "";
      return `<div class="rr-run" data-i="${i}"><span>${x.kind === "final" ? "◆" : "#" + x.n} ${esc(KIND[x.kind](x))}</span>${resTxt}
        <span class="t">${x.at ? hhmm(x.at) : x.open ? "сейчас (шаг открыт)" : ""}${x.step_ms != null ? ` · +${fmtMs(x.step_ms)}` : ""}</span>
        <span class="t">${x.similarity != null ? x.similarity + "%" : ""}</span></div>`;
    }).join("") : '<div class="empty">прогонов не было</div>';
    $$(".rr-run").forEach(el => el.onclick = () => { sel = +el.dataset.i; sub = null; renderRun(list); });
    // по умолчанию — последний прогон с упавшими тестами, иначе итог шага
    const failIdx = list.map((x, i) => [x, i]).reverse().find(([x]) => x.kind === "check" && x.check && x.check.passed !== x.check.total);
    sel = list.length ? (failIdx ? failIdx[1] : list.length - 1) : null;
    renderRun(list);
  }
  function renderRun(list) {
    disposeAll();
    $$(".rr-run").forEach(el => el.classList.toggle("sel", +el.dataset.i === sel));
    const box = $("#rr-detail");
    const x = list[sel];
    if (!x) { box.innerHTML = ""; return; }
    const tabs = [x.check && ["tests", "Тесты"], ["code", "Код на момент прогона"], x.outputs?.length && ["out", "Вывод"], ["diff", "Diff с эталоном"]].filter(Boolean);
    sub = sub && tabs.some(t => t[0] === sub) ? sub : x.kind === "run" ? "out" : x.check ? "tests" : "diff";
    box.innerHTML = `<div class="seg" style="margin-bottom:8px">${tabs.map(([k, n]) => `<button data-sub="${k}" class="${k === sub ? "sel" : ""}">${n}</button>`).join("")}</div><div class="rr-pane" id="rr-pane"></div>`;
    $$("[data-sub]", box).forEach(b => b.onclick = () => { sub = b.dataset.sub; renderRun(list); });
    const pane = $("#rr-pane", box);
    const files = Object.keys(x.code || {});
    if (sub === "tests") {
      pane.style.overflow = "auto";
      pane.innerHTML = testsHtml(x.check, { files, code: x.code });
      $$("[data-loc]", pane).forEach(b => b.onclick = () => { const [f, ln] = b.dataset.loc.split(":"); sub = "code"; renderRun(list); showCode(f, +ln); });
    } else if (sub === "code") {
      showCode(files[0], null);
    } else if (sub === "out") {
      pane.style.overflow = "auto";
      renderOutputs(pane, x.outputs, path => `/api/tasks/${r.task_id}/raw/${path}`);
    } else {
      diffSwitcher(pane, x.code?.[file] ?? "", r.references[file] || "", ["эталон", "мой код на момент прогона"]).then(d => disp.push(d));
    }
    function showCode(f, line) {
      pane.innerHTML = `<div class="rr-code" id="rr-code"></div>`;
      const model = monaco.editor.createModel(x.code?.[f] ?? "", "python");
      const ed = monaco.editor.create($("#rr-code", pane), { model, readOnly: true, automaticLayout: true, minimap: { enabled: false },
        fontFamily: "JetBrains Mono, Menlo, monospace", fontSize: 13, fontLigatures: false, scrollBeyondLastLine: false });
      disp.push({ dispose: () => { ed.dispose(); model.dispose(); } });
      // строки, на которые указывают traceback-и упавших тестов, — красные всегда
      const lines = new Set((x.check?.tests || []).filter(t => ["fail", "error"].includes(t.status)).map(t => errorLine(t.text, files, x.code)).filter(l => l && l.file === f).map(l => l.line));
      if (line) lines.add(line);
      ed.deltaDecorations([], [...lines].map(n => ({ range: new monaco.Range(n, 1, n, 1), options: { isWholeLine: true, className: "err-line", linesDecorationsClassName: "err-line-glyph" } })));
      if (line) { ed.revealLineInCenter(line); ed.setSelection(new monaco.Range(line, 1, line, model.getLineMaxColumn(line))); }
    }
  }
  $$("[data-step]").forEach(b => b.onclick = () => { step = +b.dataset.step; render(); });
  $$("[data-file]").forEach(b => b.onclick = () => { file = b.dataset.file; render(); });
  render();
}

// ---------------- Редактор задачи (та же IDE, файлы папки задачи) ----------------
async function viewEdit(id) {
  const t = await api(`/api/tasks/${id}`);
  const base = `/api/tasks/${id}`;
  const descTab = { id: "desc", label: "Описание", render: async el => {
    let text = "";
    try { text = (await api(`${base}/file?path=description.md`)).content; } catch { /* нет файла */ }
    el.innerHTML = `<div class="md">${text ? md(text) : '<p class="muted">Создайте description.md в корне задачи — его увидят в попытке.</p>'}</div>`;
  } };
  const helpTab = { id: "help", label: "Как устроено", render: el => { el.innerHTML = `<div class="md">${md(`
**Папка задачи**

- \`description.md\` — описание (markdown, формулы \`$…$\`)
- \`reference/library/\` и \`reference/scratch/\` — эталоны режимов «Библиотека» и «С нуля» (та же сигнатура). Запускаются здесь кнопкой «Запустить».
- \`starter/\` — заготовки: \`starter/model.py\` подставится в попытку вместо пустого \`model.py\`
- \`tests/test_*.py\` — общие тесты обоих режимов (pytest, \`from model import Net\`); \`tests/library/\`, \`tests/scratch/\` — проверки режима
- \`data/\` — датасеты (или подключённая папка), \`results/\` — что сохраняет код
- \`task.json\` — название, тип, тема, лимит времени, главный файл, роли

Фикстуры в тестах: \`device\`, \`seed\`, \`data_dir\`.

«Проверить» гоняет тесты на эталоне из папки — так видно, что тесты верные. «Сохранить версию» делает снимок папки: новые попытки пойдут по нему.`)}</div>`; } };
  const refPaths = arr(t.reference_paths).length ? t.reference_paths : t.reference.map(f => `reference/${f}`);  // reference/<режим>/x.py
  current = await openIDE(view, {
    title: `${t.title} · редактор задачи`, base, back: `#/task/${id}`,
    roles: Object.fromEntries(refPaths.map(p => [p, t.roles[p.split("/").pop()]]).filter(([, r]) => r)),
    open: [refPaths.find(p => p.endsWith(`/${t.main_file}`) && p.includes(`/${t.default_mode}/`)) || refPaths[0] || "description.md"],
    preload: refPaths, pyFiles: refPaths, expand: ["reference", `reference/${t.default_mode}`, "tests"],
    dataLink: t.data_link, leftTabs: [descTab, helpTab], leftTab: "desc",
    runnable: p => p.startsWith("reference/") && p.endsWith(".py"),
    run: path => api(`${base}/run`, { method: "POST", json: { path } }).then(r => r.job),
    exec: code => api(`${base}/exec`, { method: "POST", json: { code } }).then(r => r.job),
    stop: () => api(`${base}/stop`, { method: "POST" }),
    check: () => api(`${base}/check`, { method: "POST" }).then(r => r.job),
    bindData: ide => bindDataPrompt(id, ide),
    buttons: el => {
      el.innerHTML = `<span class="muted small">v${t.version}</span>
        <button class="ghost" id="x-brick" title="функция или класс под курсором станет новой задачей; здесь — from bricks.<имя> import …">Вынести в кирпичик</button>
        <button class="ghost" id="x-slot" title="функция под курсором станет слотом (сигнатура, описание) и его первой реализацией">Создать слот</button>
        <button class="primary" id="save-v" title="снимок папки: description, reference, starter, tests">Сохранить версию</button>`;
      $("#x-brick", el).onclick = () => extractBrick(id, current, false);
      $("#x-slot", el).onclick = () => extractBrick(id, current, true);
      $("#save-v", el).onclick = async () => {
        await current.saveAll();
        try { const r = await api(`${base}/version`, { method: "POST" }); toast(r.status === "unchanged" ? "изменений нет" : `сохранена версия ${r.version}`); }
        catch (e) { toast(e.message, true); }
      };
    },
  });
}

// ---------------- Статистика ----------------
async function viewStats() {
  const [st, all, mp] = await Promise.all([api("/api/stats"), apiList("/api/tasks"), api("/api/map").catch(() => ({ bricks: {}, categories: [] }))]);
  const s = st.streak, maxC = Math.max(1, ...st.calendar.map(d => d.count));
  const month = s.best_end ? new Date(s.best_end).toLocaleDateString("ru", { month: "long" }).replace(/^./, c => c) : "";
  const monthIn = month ? `в ${{ январь: "январе", февраль: "феврале", март: "марте", апрель: "апреле", май: "мае", июнь: "июне", июль: "июле", август: "августе", сентябрь: "сентябре", октябрь: "октябре", ноябрь: "ноябре", декабрь: "декабре" }[month] || month}` : "";
  // библиотека vs с нуля: доля выученных по категориям — из статусов карты (только созданные задачи)
  const bricks = Object.values(mp.bricks || {}).filter(b => b.task_id && b.kind !== "concept");
  const cats = arr(mp.categories).filter(c => c.key !== "models" || true);
  const share = (list, md) => { const own = list.filter(b => (b.statuses || {})[md] && b.statuses[md] !== "none"); return own.length ? Math.round(100 * own.filter(b => b.statuses[md] === "learned").length / own.length) : null; };
  const learnedN = md => bricks.filter(b => (b.statuses || {})[md] === "learned").length, ownN = md => bricks.filter(b => (b.statuses || {})[md] && b.statuses[md] !== "none").length;
  // слабые кирпичики: режим «слабо» на карте + последняя ошибка теста этой задачи
  const errOf = Object.fromEntries([...st.weak_tests].reverse().map(t => [t.task_id, t]));
  const weak = all.filter(t => MODES.some(m => t.mode_stats?.[m]?.learn === "weak")).map(t => {
    const m = MODES.find(md => t.mode_stats[md].learn === "weak"); return { t, m, score: t.mode_stats[m].last, err: errOf[t.id] };
  }).sort((a, b) => (a.score ?? 101) - (b.score ?? 101)).slice(0, 6);
  const tried = all.filter(t => t.attempts).sort((a, b) => (a.best_score ?? 0) - (b.best_score ?? 0)).slice(0, 3);
  const weeks = [];
  st.calendar.forEach((d, i) => { (weeks[Math.floor(i / 7)] ||= []).push(d); });
  view.innerHTML = `<div class="stats-page"><h1>Статистика</h1>
    <div class="st-top">
      <div class="card"><div class="muted">Серия</div><div class="big-n" style="font-size:34px">${s.current} ${plural(s.current, "день", "дня", "дней")}</div>
        <div class="muted">рекорд — ${s.best} ${plural(s.best, "день", "дня", "дней")}${monthIn ? `, ${monthIn}` : ""}${s.current && !s.today_done ? " · сегодня ещё не занимались" : ""}</div></div>
      <div class="card st-act"><div class="row"><span class="muted">Активность за 12 недель</span><span class="grow"></span><span class="faint small">меньше</span>
          ${[0, .35, .6, .85, 1].map(a => `<i class="lg" style="--a:${a}"></i>`).join("")}<span class="faint small">больше</span></div>
        <div class="row" style="align-items:flex-start;gap:28px;margin-top:10px">
          <div class="cal2"><div class="dn">${["пн", "", "ср", "", "пт", "", "вс"].map(d => `<span>${d}</span>`).join("")}</div>
            ${weeks.map(w => `<div class="wk">${w.map(d => `<i class="${d.count ? "on" : ""}" style="--a:${d.count ? 0.35 + 0.65 * d.count / maxC : 0}" title="${d.date}: ${d.count}"></i>`).join("")}</div>`).join("")}</div>
          <div class="st-nums"><div><b>${st.days_12w}</b> ${plural(st.days_12w, "день", "дня", "дней")} с занятиями</div><div><b>${st.hours_12w} ч</b> за 12 недель</div><div><b>${st.attempts}</b> ${plural(st.attempts, "попытка", "попытки", "попыток")}</div></div></div></div>
    </div>
    <div class="card st-vs"><div class="row st-vs-h"><h2 style="margin:0">Библиотека vs с нуля</h2>
        ${MODES.map(md => `<span class="mb mb-${md === "library" ? "lib" : "scr"}">${ICON[MODE_ICON[md]]}${MODE_NAME[md]} · ${learnedN(md)} из ${ownN(md)} выучено</span>`).join("")}
        <span class="grow"></span>${st.mode_lag_days != null ? `<span class="muted small">«с нуля» в среднем отстаёт от применения на ${st.mode_lag_days} ${plural(st.mode_lag_days, "день", "дня", "дней")}</span>` : ""}</div>
      <div class="vs-grid"><span></span><span class="faint small">библиотека — доля выученных</span><span></span><span class="faint small">с нуля — доля выученных</span><span></span>
        ${cats.map(c => { const list = bricks.filter(b => arr(b.categories).includes(c.key)); if (!list.length) return "";
          return `${catTag(c.key, c.title)}${MODES.map(md => { const v = share(list, md);
            return `<div class="vs-bar"><i class="${md}" style="width:${v ?? 0}%"></i></div><span class="mono-num">${v == null ? "—" : `${v}%`}</span>`; }).join("")}`; }).join("")}</div></div>
    <div class="st-bottom">
      <div class="card"><h2>Слабые темы</h2>${st.weak_tags.filter(t => t.avg_score != null).length ? st.weak_tags.filter(t => t.avg_score != null).slice(0, 6).map(t => `<div class="wt"><span>${esc(t.tag)}</span>
          <div class="vs-bar"><i style="width:${t.avg_score}%;background:${t.avg_score >= 80 ? "var(--ok)" : t.avg_score >= 60 ? "var(--due)" : "var(--fail)"}"></i></div><b class="mono-num">${t.avg_score}</b></div>`).join("")
          + '<p class="faint small">средняя оценка по сданным попыткам</p>' : emptyState({ icon: "check", tone: "ok", title: "Пока нечего показать", text: "Сдайте несколько попыток." })}</div>
      <div class="card st-weak"><h2>Слабые кирпичики</h2>${weak.length ? weak.map(w => `<div class="trow2" data-t="${w.t.id}"><div class="tr-main"><div class="tr-name"><b class="mono">${esc(w.t.name)}</b><span class="faint"> · ${MODE_NAME[w.m]}</span></div>
          <div class="muted small">${w.err ? esc(`${w.err.test}: ${w.err.last_error}`.slice(0, 110)) : "прошлый раз ошибся"}</div></div>
          ${w.score != null ? `<span class="score-b ${w.score >= 70 ? "ok" : w.score >= 50 ? "warn" : "err"}">${w.score}</span>` : ""}</div>`).join("")
          : emptyState({ icon: "check", tone: "ok", title: "Слабых нет", text: "Все кирпичики в порядке." })}</div>
      <div class="card"><div class="row"><h2 style="margin:0">По задаче</h2><span class="grow"></span>${tried.length ? `<div class="seg" style="margin:0">${tried.map((t, i) => `<button data-pt="${t.id}" class="mono ${i ? "" : "sel"}">${esc(t.name)}</button>`).join("")}</div>` : ""}</div>
        <div id="prog" class="mt">${tried.length ? "" : emptyState({ icon: "flask", title: "Сданных попыток нет", text: "" })}</div></div>
    </div></div>`;
  $$(".st-weak [data-t]").forEach(tr => tr.onclick = () => { location.hash = `#/task/${tr.dataset.t}`; });
  const show = async tid => {
    const list = (await api(`/api/tasks/${tid}/attempts`)).filter(a => a.status === "submitted").reverse().slice(-8);
    const sc = list.map(a => a.score ?? 0), tm = list.map(a => Math.round((a.total_ms || 0) / 60000));
    const line = (vals, cls) => { if (!vals.length) return ""; const W = 300, H = 70, mx = Math.max(...vals), mn = Math.min(...vals);
      const x = i => vals.length === 1 ? W / 2 : i * W / (vals.length - 1), y = v => H - 8 - (mx === mn ? .5 : (v - mn) / (mx - mn)) * (H - 16);
      return `<svg viewBox="0 0 ${W} ${H}" class="spark ${cls}" preserveAspectRatio="none"><path d="${vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("")}"/></svg>`; };
    $("#prog").innerHTML = list.length ? `<div class="row"><span class="muted">Оценка</span><span class="grow"></span><span class="faint small">от ${Math.min(...sc)} до ${Math.max(...sc)}</span></div>${line(sc, "")}
      <div class="row mt"><span class="muted">Время, мин</span><span class="grow"></span><span class="faint small">от ${Math.min(...tm)} до ${Math.max(...tm)} мин</span></div>${line(tm, "t")}
      <p class="faint small">${list.length} ${plural(list.length, "попытка", "попытки", "попыток")} · последняя справа</p>` : '<p class="muted">сданных попыток нет</p>';
  };
  $$("[data-pt]").forEach(b => b.onclick = () => { $$("[data-pt]").forEach(x => x.classList.toggle("sel", x === b)); show(b.dataset.pt); });
  if (tried.length) show(tried[0].id);
}

// ---------------- Настройки ----------------
async function viewSettings() {
  const s = await api("/api/settings");
  // параметры оценки как ползунки (это реальные штрафы оценки, а не доли)
  const W = [["free_checks", "«Проверить» без штрафа", "раз", 10], ["check_penalty", "«Проверить»", "каждое следующее — минус", 30], ["check_penalty_max", "«Проверить», не больше", "потолок штрафа", 60],
    ["ref_penalty", "Эталон", "подсмотр — минус", 50], ["time_penalty", "Время", "дольше прошлой попытки — минус", 40], ["slower_pct", "…дольше больше чем на", "%", 100]];
  const sec = [["env", "Окружение Python"], ["llm", "LLM-судья"], ["w", "Веса оценки"], ["bk", "Бэкапы"], ["map", "Импорт карты"], ["theme", "Тема"]];
  view.innerHTML = `<div class="settings-page"><h1>Настройки</h1><div class="set-grid">
    <nav class="set-nav">${sec.map(([k, n], i) => `<a href="#" data-sec="${k}" class="${i ? "" : "active"}">${n}</a>`).join("")}</nav>
    <div>
      <section class="card" id="sec-env"><div class="row"><h2 style="margin:0">Окружение Python</h2><span id="env-st"></span><span class="grow"></span><button class="small" id="env-check">Проверить окружение</button></div>
        <label class="fld">Интерпретатор приложения<div class="env-path"><span class="mono" id="env-py">…</span><span class="faint" id="env-v"></span></div></label>
        <div class="chips" id="env-pk"></div><p class="faint small">Окружение конкретной задачи и лимит времени на запуск — в настройках задачи.</p></section>
      <section class="card" id="sec-llm"><div class="row"><h2 style="margin:0">LLM-судья</h2><span class="grow"></span><label class="switch"><input type="checkbox" id="judge" ${+s.llm_judge ? "checked" : ""}><i></i></label></div>
        <p class="muted">Комментирует код после сдачи: короткая причина ошибки и отличия от эталона. На оценку и прохождение тестов не влияет.</p>
        <div class="two"><label class="fld">Провайдер<select id="prov"><option value="ollama" ${s.llm_provider === "ollama" ? "selected" : ""}>Ollama (локально)</option><option value="groq" ${s.llm_provider === "groq" ? "selected" : ""}>Groq API</option></select></label>
          <label class="fld">Ollama URL<input id="o-url" value="${esc(s.ollama_url)}"></label>
          <label class="fld">Модель Ollama<input id="o-model" value="${esc(s.ollama_model)}"></label>
          <label class="fld">Модель Groq<input id="g-model" value="${esc(s.groq_model)}"><span class="${s.groq_key_set ? "ok" : "warn"} small">GROQ_API_KEY ${s.groq_key_set ? "задан" : "не задан (.env)"}</span></label></div>
        <div class="row"><button class="small" id="test">Проверить связь</button><span id="test-out" class="small"></span></div></section>
      <section class="card" id="sec-w"><div class="row"><h2 style="margin:0">Веса оценки</h2><span class="grow"></span><span class="faint small">оценка = 100 · доля прошедших тестов − штрафы</span></div>
        ${W.map(([k, n, hint, max]) => `<div class="wrow"><div><div>${n}</div><div class="faint small">${hint}</div></div>
          <input type="range" min="0" max="${max}" value="${s[k]}" data-k="${k}"><b class="mono-num" data-v="${k}">${s[k]}</b></div>`).join("")}
        <p class="faint small">Уровень повторения: ≥90 легко, ≥70 нормально, ≥50 трудно, иначе забыл; открытый эталон — на уровень ниже.</p></section>
      <section class="card" id="sec-bk"><div class="row"><h2 style="margin:0">Бэкапы</h2><span class="faint mono small">data/backups</span><span class="grow"></span>
          <a class="btn small" href="/api/backup/export" download>Экспорт .zip</a><button class="small" id="imp">Загрузить бэкап…</button><input type="file" id="imp-file" accept=".zip" hidden>
          <button class="primary small" id="bk-now">Сделать копию сейчас</button></div>
        <div class="two mt"><div><div class="bk-h"><b>Автокопии</b><span class="faint small">раз в день · хранятся 7 последних</span></div><div class="bk-list" id="bk-auto"></div></div>
          <div><div class="bk-h"><b>Ручные копии</b><span class="faint small">отдельная папка · не удаляются сами</span></div><div class="bk-list" id="bk-man"></div>
            <p class="faint small">Копии перед миграциями и импортом. Восстановить — «Загрузить бэкап».</p></div></div></section>
      <section class="card" id="sec-map"></section>
      <section class="card" id="sec-theme"><div class="row"><h2 style="margin:0">Тема</h2><span class="grow"></span>
        <div class="seg" style="margin:0">${[["dark", "Тёмная"], ["light", "Светлая"], ["system", "Как в системе"]].map(([k, n]) => `<button data-th="${k}" class="${themePref() === k ? "sel" : ""}">${n}</button>`).join("")}</div>
        <div class="seg" style="margin:0">${[13, 14].map(n => `<button data-fs="${n}" class="${store.get("code.fs", 13) === n ? "sel" : ""}">Код ${n} px</button>`).join("")}</div></div></section>
    </div></div></div>`;
  const save = () => api("/api/settings", { method: "PUT", json: {
    ...Object.fromEntries($$("[data-k]").map(i => [i.dataset.k, Math.max(0, +i.value || 0)])), llm_judge: $("#judge").checked ? 1 : 0,
    llm_provider: $("#prov").value, ollama_url: $("#o-url").value, ollama_model: $("#o-model").value, groq_model: $("#g-model").value } });
  let t = null;
  const autosave = () => { clearTimeout(t); t = setTimeout(async () => { await save(); toast("настройки сохранены"); }, 500); };
  $$("[data-k]").forEach(i => i.oninput = () => { $(`[data-v="${i.dataset.k}"]`).textContent = i.value; autosave(); });
  ["#judge", "#prov", "#o-url", "#o-model", "#g-model"].forEach(id => $(id).onchange = autosave);
  $$("[data-sec]").forEach(a => a.onclick = e => { e.preventDefault(); $$("[data-sec]").forEach(x => x.classList.toggle("active", x === a)); $(`#sec-${a.dataset.sec}`).scrollIntoView({ behavior: "smooth", block: "start" }); });
  const env = async () => {
    $("#env-st").innerHTML = '<span class="faint spinner small">проверяю</span>';
    try {
      const r = await api("/api/python/check", { method: "POST", json: { path: "" } });
      $("#env-st").innerHTML = `<span class="badge dot ${r.pytest ? "ok" : "err"}">${r.pytest ? "работает" : "нет pytest"}</span>`;
      $("#env-py").textContent = r.python; $("#env-v").textContent = r.version;
      $("#env-pk").innerHTML = r.packages.map(p => `<span class="tag">${esc({ sklearn: "scikit-learn" }[p] || p)} ${esc((r.versions?.[p] || "").split(".").slice(0, 2).join("."))}</span>`).join("")
        + (r.pytest ? "" : `<span class="err small">установите: <span class="mono">${esc(r.fix)}</span></span>`);
    } catch (e) { $("#env-st").innerHTML = `<span class="badge err">${esc(e.message)}</span>`; }
  };
  env();
  $("#env-check").onclick = env;
  $("#test").onclick = async () => {
    await save();
    $("#test-out").innerHTML = '<span class="muted spinner">спрашиваю модель</span>';
    const r = await api("/api/settings/test", { method: "POST" });
    $("#test-out").innerHTML = r.ok ? `<span class="ok">ok</span> · ${esc(r.provider)} · ${esc(r.model)} · ${(r.ms / 1000).toFixed(1)} с: «${esc(r.answer)}»` : `<span class="err">нет связи: ${esc(r.answer)}</span>`;
  };
  const row = b => `<div class="bk-row"><span class="mono">${esc(b.name)}</span><span class="faint small">${fmtDate(b.created)}</span><span class="grow"></span><span class="faint small">${fmtSize(b.size)}</span>
    <a class="small" href="/api/backup/file?name=${encodeURIComponent(b.name)}" download>Скачать</a></div>`;
  const list = l => {
    $("#bk-auto").innerHTML = l.filter(b => b.auto).map(row).join("") || '<p class="faint small" style="padding:8px">копий нет</p>';
    $("#bk-man").innerHTML = l.filter(b => !b.auto).map(row).join("") || '<p class="faint small" style="padding:8px">копий нет</p>';
  };
  mapSettingsCard($("#sec-map"));
  api("/api/backup/list").then(list);
  $("#bk-now").onclick = async () => { const r = await api("/api/backup/now", { method: "POST" }); list(r.backups); toast(r.made ? `создана ${r.made}` : "сегодняшняя копия уже есть"); };
  $("#imp").onclick = () => $("#imp-file").click();
  $("#imp-file").onchange = async e => {
    const f = e.target.files[0];
    if (!f || !confirm(`Заменить базу содержимым «${f.name}»? Текущая база перед этим сохранится в ручные копии.`)) return;
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/backup/import", { method: "POST", body: fd }); toast(`импортировано задач: ${r.tasks}`); api("/api/backup/list").then(list); }
    catch (err) { toast(err.message, true); }
  };
  $$("[data-th]").forEach(b => b.onclick = () => { setTheme(b.dataset.th); $$("[data-th]").forEach(x => x.classList.toggle("sel", x === b)); paintTheme(); });
  $$("[data-fs]").forEach(b => b.onclick = () => { store.set("code.fs", +b.dataset.fs); $$("[data-fs]").forEach(x => x.classList.toggle("sel", x === b)); });
}
