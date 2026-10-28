// CODE RECALL — экраны: «Сегодня», «Задачи», задача, решение (IDE), статистика, настройки.
const view = $("#view");
let current = null;  // открытая IDE — закрываем при уходе со страницы

$("#theme").onclick = () => setTheme(theme() === "dark" ? "light" : "dark");

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
  const nav = { task: "tasks", attempt: "journal", edit: "tasks", review: "journal", assemble: "tasks", map: "map", builder: "tasks" }[name] || name || "today";
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

// ---------------- Сегодня ----------------
async function viewToday() {
  const t = await api("/api/today");
  const section = (items, title, cls, empty) => `<div class="card"><div class="row" style="margin-bottom:6px"><h2 style="margin:0">${title}</h2>
      <span class="badge ${cls}">${items.length}</span></div>
    ${items.length ? `<div class="scroll-x"><table><tbody>${items.map(r => `<tr class="link" data-id="${r.id}">
      <td style="width:28px">${statusCell(cls === "muted" ? "new" : cls === "ok" ? "solved" : "due")}</td>
      <td><span class="title">${esc(r.title)}</span> <span class="badge mode-${r.mode}">${esc(r.mode_name || "")}</span><div class="muted small">${esc(r.reason)}</div></td>
      <td>${kindBadge(r.kind)}</td><td class="muted">${esc(r.tag || "")}</td>
      <td class="nowrap muted">${r.due_at || ""}</td>
      <td class="nowrap" style="text-align:right"><button class="${cls === "muted" ? "" : "primary"} small" data-go="${r.id}" data-mode="${r.mode || ""}">${r.active_attempt ? "продолжить" : "решать"}</button></td>
    </tr>`).join("")}</tbody></table></div>` : `<div class="empty">${empty}</div>`}</div>`;
  const total = t.overdue.length + t.due.length;
  const reviewsCard = t.reviews.length ? `<div class="card"><div class="row" style="margin-bottom:6px"><h2 style="margin:0">Работа над ошибками</h2>
      <span class="badge warn">${t.reviews.length}</span></div><table><tbody>${t.reviews.map(r => `<tr class="link" data-review="${r.id}">
        <td style="width:28px"><span class="status-ico warn">✎</span></td>
        <td><span class="title">${esc(r.title)}</span> <span class="badge mode-${r.mode}">${esc(r.mode_name || "")}</span><div class="muted small">${esc(r.reason)}</div></td>
        <td>${kindBadge(r.kind)}</td><td class="muted nowrap">${fmtDate(r.started_at)}</td>
        <td style="text-align:right"><button class="primary small">продолжить</button></td></tr>`).join("")}</tbody></table></div>` : "";
  view.innerHTML = `<div class="row" style="margin-bottom:14px"><h1 style="margin:0">Сегодня</h1>
      <span class="muted">${total ? `к повторению: ${total}` : "повторений на сегодня нет"}${t.new.length ? ` · новых задач: ${t.new.length}` : ""}</span></div>
    ${reviewsCard}
    ${section(t.overdue, "Просрочено", "err", "ничего не просрочено")}
    ${section(t.due, "На сегодня", "warn", "на сегодня всё повторено")}
    ${section(t.new, "Новые", "muted", 'новых задач нет — <a href="#/tasks">загрузите задачи</a>')}
    ${t.upcoming.length ? section(t.upcoming, "Ближайшие 7 дней", "ok", "") : ""}`;
  $$("[data-go]").forEach(b => b.onclick = e => { e.stopPropagation(); startAttempt(b.dataset.go, b.dataset.mode); });
  $$("tr[data-id]").forEach(tr => tr.onclick = () => { location.hash = `#/task/${tr.dataset.id}`; });
  $$("tr[data-review]").forEach(tr => tr.onclick = () => { location.hash = `#/review/${tr.dataset.review}`; });
}

// ---------------- Задачи (как список задач LeetCode) ----------------
const lib = { q: "", kind: "", status: "", tags: [], topic: undefined, sort: "title", dir: 1 };
async function viewTasks() {
  // дерево тем — необязательная часть: не загрузилось — библиотека всё равно открывается, без дерева
  const [rawTasks, topics, planned] = await Promise.all([api("/api/tasks"), apiList("/api/topics"), apiList("/api/map/planned")]);
  const tasks = arr(rawTasks).map(normTask);
  lib.topic ??= store.get("lib.topic", null);
  if (lib.topic != null && !topics.some(t => t.id === lib.topic)) lib.topic = null;
  const allTags = [...new Set(tasks.flatMap(t => t.tags))].sort();
  const cols = [["status", ""], ["title", "Название"], ["kind", "Тип"], ["topic", "Узел"], ["best_score", "Лучшая оценка"], ["attempts", "Попыток"], ["due_at", "Повтор"]];
  tasks.forEach(t => { t.topic = topicPath(topics, t.topic_id); });
  view.innerHTML = `
    <div class="row" style="margin-bottom:14px"><h1 style="margin:0">Библиотека</h1><span class="muted">${tasks.length}</span><span class="grow"></span>
      <button id="new">＋ Новая задача</button><button class="primary" id="upload">⇪ Загрузить папки</button></div>
    <div class="libgrid ${store.get("lib.treeHidden", false) ? "tree-hidden" : ""}" id="libgrid">
      <div class="card libtree" id="tree"></div>
      <div class="card" style="min-width:0">
        <div class="row" style="margin-bottom:10px">
          <button class="icon-btn" id="tree-toggle" title="показать / скрыть дерево тем">☰</button>
          <input id="q" placeholder="Поиск задач" value="${esc(lib.q)}" style="min-width:200px">
          <select id="f-kind"><option value="">Все типы</option><option value="algo" ${lib.kind === "algo" ? "selected" : ""}>Алгоритм</option><option value="ml" ${lib.kind === "ml" ? "selected" : ""}>ML</option></select>
          <select id="f-status"><option value="">Любой статус</option>${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${lib.status === k ? "selected" : ""}>${v[2]}</option>`).join("")}
            <option value="planned" ${lib.status === "planned" ? "selected" : ""}>запланировано</option><option value="noplan" ${lib.status === "noplan" ? "selected" : ""}>без запланированных</option></select>
        </div>
        ${allTags.length ? `<div class="row" style="margin-bottom:10px;flex-wrap:wrap"><span class="muted small">теги:</span>${allTags.map(g => `<button class="small ${lib.tags.includes(g) ? "sel" : "ghost"}" data-tag="${esc(g)}">${esc(g)}</button>`).join("")}</div>` : ""}
        <div class="scroll-x"><table><thead><tr>${cols.map(([k, n]) => `<th class="sort" data-k="${k}">${n}${lib.sort === k ? (lib.dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead>
          <tbody id="rows"></tbody></table></div>
        ${tasks.length ? "" : '<div class="empty">Задач пока нет. Перетащите папку задачи (reference/, tests/, description.md) — например из examples/.</div>'}
      </div></div>`;
  const rank = { due: 0, new: 1, solved: 2 };
  let kids = {};
  const render = () => {
    const inTopic = lib.topic == null ? null : new Set(subtreeIds(kids, lib.topic));
    const st = ["planned", "noplan"].includes(lib.status) ? "" : lib.status;
    const rows = tasks.filter(t => lib.status !== "planned" && (!lib.kind || t.kind === lib.kind) && (!st || t.status === st)
        && (!inTopic || inTopic.has(t.topic_id)) && lib.tags.every(g => t.tags.includes(g))
        && (t.title + " " + t.name + " " + t.topic + " " + t.tags.join(" ")).toLowerCase().includes(lib.q.toLowerCase()))
      .sort((a, b) => {
        let x = a[lib.sort], y = b[lib.sort];
        if (lib.sort === "status") { x = rank[x]; y = rank[y]; }
        if (x == null) return 1; if (y == null) return -1;
        return (typeof x === "string" ? x.localeCompare(y) : x - y) * lib.dir;
      });
    const plan = lib.status && lib.status !== "planned" || lib.kind || lib.tags.length ? [] : planned.filter(p => (!inTopic || inTopic.has(p.topic_id))
      && (p.name + " " + p.note + " " + arr(p.categories).join(" ")).toLowerCase().includes(lib.q.toLowerCase()));
    $("#rows").innerHTML = rows.map(t => `<tr class="link" data-id="${t.id}" draggable="true" title="перетащите на узел дерева, чтобы перенести">
      <td style="width:56px">${modeHalves(t.statuses)}</td>
      <td><span class="title">${esc(t.title)}</span>${t.active_attempt ? ' <span class="badge warn">в процессе</span>' : ""}
        ${TYPE_BADGE[t.type] ? ` <span class="badge">${TYPE_BADGE[t.type][1]}${t.implements ? ` · ${esc(t.implements)}` : ""}</span>` : ""}
        ${t.broken ? ` <span class="badge err" title="${esc(t.broken)}">сломано зависимостью</span>` : ""}
        ${t.tags.length ? `<div class="muted small">${t.tags.map(g => "#" + esc(g)).join(" ")}</div>` : ""}</td>
      <td>${kindBadge(t.kind)}</td><td class="muted small">${esc(t.topic || "—")}</td>
      <td>${t.best_score != null ? `<span class="${t.best_score >= 70 ? "ok" : t.best_score >= 50 ? "warn" : "err"}">${t.best_score}</span>` : '<span class="muted">—</span>'}</td>
      <td class="muted">${t.attempts}</td><td class="muted nowrap">${t.due_at ? t.due_at.slice(0, 10) : "—"}</td></tr>`).join("")
      + plan.map(p => `<tr class="link planned" data-plan="${esc(p.name)}" title="кирпичик карты — задачи ещё нет; клик — создать в мастере">
        <td style="width:28px"><span class="status-ico muted">◌</span></td><td><span class="title">${esc(p.name)}</span> <span class="badge">${p.kind === "concept" ? "концепт" : "запланировано"}</span>
          ${p.note ? `<div class="muted small">${esc(p.note)}</div>` : ""}</td><td></td><td class="muted small">${esc(topicPath(topics, p.topic_id) || "—")}</td>
        <td class="muted">—</td><td class="muted">—</td><td class="muted small">в ${p.rows.length} стр. карты</td></tr>`).join("")
      || '<tr><td colspan="7" class="empty">ничего не найдено</td></tr>';
    $$("#rows tr[data-id]").forEach(tr => tr.ondragstart = e => e.dataTransfer.setData("text/task", tr.dataset.id));
  };
  // выбор узла — перерисовать дерево и таблицу; правка дерева (создать, перенести…) — перечитать всё
  const onTree = (reload = true) => { if (reload) return viewTasks(); kids = renderTopicTree($("#tree"), topics, lib, onTree); render(); };
  kids = renderTopicTree($("#tree"), topics, lib, onTree);
  render();
  $("#tree-toggle").onclick = () => { const g = $("#libgrid"); g.classList.toggle("tree-hidden"); store.set("lib.treeHidden", g.classList.contains("tree-hidden")); };
  $$("[data-tag]").forEach(b => b.onclick = () => { const g = b.dataset.tag; lib.tags = lib.tags.includes(g) ? lib.tags.filter(x => x !== g) : [...lib.tags, g]; viewTasks(); });
  $("#q").oninput = e => { lib.q = e.target.value; render(); };
  $("#f-kind").onchange = e => { lib.kind = e.target.value; render(); };
  $("#f-status").onchange = e => { lib.status = e.target.value; render(); };
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
async function viewTask(id, tab = "about") {
  const t = normTask(await api(`/api/tasks/${id}`));
  view.innerHTML = `
    <div class="row" style="margin-bottom:6px"><a href="#/tasks" class="muted">← Библиотека</a></div>
    <div class="row" style="margin-bottom:14px"><h1 style="margin:0">${esc(t.title)}</h1>${kindBadge(t.kind)}
      ${TYPE_BADGE[t.type] ? `<span class="badge">${TYPE_BADGE[t.type][1]}${t.implements ? ` · слот ${esc(t.implements)}` : ""}</span>` : ""}
      ${t.tags.map(g => `<span class="badge">#${esc(g)}</span>`).join("")}
      ${modeHalves(t.statuses)}<span class="grow"></span>
      <button class="ghost" id="dup" title="копия задачи со всеми файлами">Дублировать</button>
      <a class="btn" href="#/edit/${t.id}">✎ Редактировать задачу</a>
      <a class="btn" href="#/builder/${t.id}" title="визуальная доска: зависимости, «Собрать в блок», эталоны обоих режимов">Конструктор</a>
      ${t.modes.length ? `<div class="seg" id="mode-seg" style="margin:0" title="Библиотека — как и где применять; С нуля — как работает. Засчитываются оба.">
        ${MODES.map(m => `<button data-mode="${m}" ${t.modes.includes(m) ? "" : 'disabled title="у задачи нет этого режима"'}>${MODE_TITLE[m]}</button>`).join("")}</div>
      <button class="primary" id="go">${t.deps.length ? "Собрать и начать" : "Начать"}</button>` : '<span class="badge">концепт — только README</span>'}</div>
    ${t.broken ? `<div class="card" style="border-left:3px solid var(--err)"><b class="err">Сломано зависимостью</b> — ${esc(t.broken)}
      <span class="muted small">Тесты задачи упали на эталоне после смены эталона кирпичика; такие тесты не влияют на оценку.</span>
      <button class="small" id="recheck">Перепроверить</button></div>` : ""}
    <div class="tabs">${[["about", "Описание"], ["compose", "Состав"], ["attempts", "Попытки"], ["versions", "Версии"], ["settings", "Настройки"]]
      .map(([k, n]) => `<a href="#/task/${id}/${k}" class="${k === tab ? "active" : ""}">${n}</a>`).join("")}</div>
    <div id="tab"></div>`;
  let mode = store.get(`mode.${t.id}`, t.default_mode);
  if (!t.modes.includes(mode)) mode = t.default_mode;
  const paintMode = () => $$("#mode-seg [data-mode]").forEach(b => b.classList.toggle("sel", b.dataset.mode === mode));
  $$("#mode-seg [data-mode]").forEach(b => b.onclick = () => { mode = b.dataset.mode; store.set(`mode.${t.id}`, mode); paintMode(); });
  paintMode();
  const go = $("#go");
  if (go) go.onclick = () => startAttempt(t.id, mode);
  $("#dup").onclick = async () => { const r = await api(`/api/tasks/${t.id}/duplicate`, { method: "POST" }); toast("копия создана"); location.hash = `#/task/${r.id}`; };
  const rc = $("#recheck");
  if (rc) rc.onclick = async () => { rc.disabled = true; const { job } = await api(`/api/tasks/${t.id}/recheck`, { method: "POST" }); await followJob(job, () => {}); viewTask(id, tab); };
  const box = $("#tab");
  if (tab === "compose") return renderComposition(box, id);
  if (tab === "about") {
    box.innerHTML = `<div class="card"><div class="md">${t.description ? md(t.description) : '<p class="muted">Описания нет — добавьте description.md в редакторе задачи.</p>'}</div></div>
      <div class="card"><div class="row"><span class="label" style="margin:0">Файлы эталона</span></div>
        <div class="mt">${t.reference.map(f => `<span class="badge">${esc(f)} · ${t.roles[f] === "given" ? "дан" : "пишу сам"}</span>`).join(" ")}</div>
        <div class="muted small mt">тестов: ${t.test_files.map(esc).join(", ") || "нет"} · лимит времени ${t.timeout} с · версия ${t.version}${t.dirty ? ' · <span class="warn">в папке есть несохранённые изменения</span>' : ""}</div>
        ${t.deps.length ? `<div class="label mt">Зависимости</div>${t.deps.map(d => `<div class="small mono">${d.slot ? `from slots.${esc(d.slot)} import …  <span class="muted">(слот: реализация выбирается при сборке)</span>` : `from bricks.${esc(d.name)} import …  <span class="muted">← ${esc(d.task)}</span>`}</div>`).join("")}` : ""}</div>`;
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
const JFILTERS = [["", "Все"], ["abandoned", "Только брошенные"], ["errors", "С ошибками"], ["reviews", "Работа над ошибками"]];

// Таблица попыток и «работы над ошибками». opts.task_id — только одна задача.
async function journalTable(box, opts = {}, filter = "") {
  const q = new URLSearchParams({ filter, ...(opts.task_id ? { task_id: opts.task_id } : {}) });
  const rows = await api(`/api/journal?${q}`);
  box.innerHTML = `<div class="row" style="margin-bottom:10px">${JFILTERS.map(([k, n]) => `<button class="small ${k === filter ? "sel" : "ghost"}" data-f="${k}">${n}</button>`).join("")}</div>
    ${rows.length ? `<div class="scroll-x"><table><thead><tr><th>Дата</th>${opts.task_id ? "" : "<th>Задача</th>"}<th>Тип</th><th>Статус</th><th>Оценка</th><th>Время</th><th>«Проверить»</th><th>Эталон</th><th></th></tr></thead><tbody>
    ${rows.map(r => `<tr class="link" data-open="${r.type === "review" ? `#/review/${r.id}${r.status === "active" ? "" : "/report"}` : `#/attempt/${r.id}`}">
      <td class="nowrap muted">${fmtDate(r.date)}</td>${opts.task_id ? "" : `<td><span class="title">${esc(r.task)}</span></td>`}
      <td>${r.mode ? `<span class="badge mode-${r.mode}">${esc(r.mode_name)}</span> ` : ""}${r.type === "review" ? `<span class="badge">работа над ошибками</span>${r.status === "active" ? ` <span class="muted small">шаг ${r.step}/3</span>` : ""}` : '<span class="badge">попытка</span>'}</td>
      <td><span class="badge ${JSTATUS[r.status] || ""}">${esc(r.status_name)}</span>${r.reason ? `<div class="muted small" style="min-width:220px;max-width:380px">${esc(r.reason)}</div>` : ""}</td>
      <td>${r.score ?? '<span class="muted">—</span>'}</td><td class="mono muted">${fmtMs(r.total_ms)}</td>
      <td class="muted">${r.checks}</td><td>${r.ref_opened ? `<span class="warn small">${r.type === "review" ? "подглядывал" : "открывал"}</span>` : '<span class="muted">—</span>'}</td>
      <td style="text-align:right">${r.type === "attempt" && ["abandoned", "partial", "passed"].includes(r.status)
        ? `<button class="small ${r.status === "passed" ? "ghost" : "primary"}" data-review="${r.id}">Работа над ошибками</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>` : '<div class="empty">записей нет</div>'}`;
  $$("[data-f]", box).forEach(b => b.onclick = () => journalTable(box, opts, b.dataset.f));
  $$("tr[data-open]", box).forEach(tr => tr.onclick = e => { if (!e.target.closest("button")) location.hash = tr.dataset.open; });
  $$("[data-review]", box).forEach(b => b.onclick = e => { e.stopPropagation(); startReview(+b.dataset.review); });
  return rows;
}

async function viewJournal() {
  view.innerHTML = '<h1>Журнал</h1><p class="muted">Все попытки — сданные, брошенные и с ошибками — и «работа над ошибками». Клик — открыть только для чтения.</p><div class="card" id="jr"></div>';
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

// ---------------- Решение (IDE) ----------------
const OUTCOME_TITLE = { abandoned: "брошена", passed: "сдана", partial: "тесты частично", checking: "проверяется" };

async function viewAttempt(id) {
  let a = await api(`/api/attempts/${id}`);
  const readonly = a.status !== "active";
  const base = `/api/attempts/${id}`;
  const loadedAt = Date.now(), baseMs = a.total_ms;
  const totalMs = () => readonly ? a.total_ms : baseMs + (Date.now() - loadedAt);
  const written = a.files.filter(f => a.roles[f] !== "given");  // свои файлы «пишу сам» и кирпичики bricks/…
  const brickOf = Object.fromEntries((a.bricks || []).filter(b => b.module).map(b => [b.module, b]));
  let refFiles = null;
  if (readonly) refFiles = (await api(`${base}/reference`, { method: "POST" })).files;  // после окончания — без штрафа
  const needsWork = readonly && (a.outcome === "abandoned" || a.outcome === "partial");

  const leftTabs = [
    { id: "desc", label: "Описание", render: el => { el.innerHTML = `<h2>${esc(a.title)}</h2><div class="row" style="margin-bottom:10px">${kindBadge(a.kind)}${a.tag ? `<span class="badge">${esc(a.tag)}</span>` : ""}
        <span class="muted small">v${a.version} · лимит ${a.timeout} с</span></div>
      <div class="md">${a.description ? md(a.description) : '<p class="muted">описания нет</p>'}</div>
      <div class="label mt">Файлы</div>${a.files.map(f => `<div class="small"><span class="mono">${esc(f)}</span> — ${a.roles[f] === "given" ? "дан" : brickOf[f] ? `кирпичик «${esc(brickOf[f].title)}», пишу сам` : "пишу сам"}</div>`).join("")}`; } },
    ...(readonly ? [{ id: "report", label: a.report?.weights ? "Отчёт" : "Итог", render: el => a.report?.weights ? renderReport(el, a, na => { a = na; }) : renderAbandoned(el, a) }] : []),
    { id: "attempts", label: "Попытки", render: async el => {
      const list = await api(`/api/tasks/${a.task_id}/attempts`);
      const done = list.filter(x => x.score != null).reverse();
      el.innerHTML = `${list.map(x => `<div class="row small" style="padding:4px 0;border-bottom:1px solid var(--line)"><a href="#/attempt/${x.id}">${fmtDate(x.date)}</a>
          <span class="badge ${JSTATUS[x.status] || ""}">${esc(x.status_name)}</span><span class="grow"></span>${x.score != null ? `<b>${x.score}</b>` : ""}<span class="mono muted">${fmtMs(x.total_ms)}</span></div>`).join("")}
        ${done.length ? '<div id="h" class="mt"></div>' : ""}`;
      if (done.length) historyCharts($("#h", el), done.map(x => ({ date: x.finished_at, score: x.score, total_ms: x.total_ms })));
    } },
    ...(readonly ? [] : [{ id: "ref", label: "Эталон", render: el => renderReference(el, a, base, readonly, () => refFiles, f => { refFiles = f; a.ref_opened = true; }) }]),
    ...((a.bricks || []).length ? [{ id: "asm", label: "Сборка", render: el => renderAssemblyTab(el, a) }] : []),
  ];

  current = await openIDE(view, {
    title: `${a.title} · ${MODE_NAME[a.mode] || a.mode}` + (readonly ? ` · ${OUTCOME_TITLE[a.outcome] || a.outcome}` : ""), base, readonly, back: `#/task/${a.task_id}`,
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
    buttons: (el, ide) => {
      el.innerHTML = `<span class="timer" id="timer" title="время попытки">${fmtMs(totalMs())}</span>
        ${readonly ? `<span class="badge ${JSTATUS[a.outcome] || ""}">${OUTCOME_TITLE[a.outcome] || a.outcome}</span>${a.score != null ? `<b>${a.score}</b>` : ""}
            ${a.status !== "checking" ? `<button class="${needsWork ? "primary" : "ghost"}" id="work">${needsWork ? "Работа над ошибками сейчас" : "Работа над ошибками"}</button>` : ""}`
          : `<span class="muted small" id="checks"></span><button class="icon-btn" id="reset" title="вернуть текущий файл к заготовке">↺ файл</button>
             <button class="ghost" id="abandon" title="закончить без сдачи: попытка сохранится как брошенная">Сбросить</button><button class="primary" id="submit">Сдать</button>`}`;
      if (readonly) {
        const w = $("#work", el);
        if (w) w.onclick = () => startReview(a.id);
        return;
      }
      $("#reset", el).onclick = async () => {
        const p = ide.current;
        if (!p || !a.files.includes(p)) return toast("откройте файл задачи", true);
        if (!confirm(`Вернуть ${p} к заготовке? Текущий код этого файла пропадёт.`)) return;
        const r = await api(`${base}/reset`, { method: "POST", json: { path: p } });
        ide.models[p].setValue(r.content);
        await ide.save(p);
      };
      $("#abandon", el).onclick = async () => {
        if (!confirm("Сбросить попытку? Она сохранится в истории как брошенная (со всем кодом), в повторениях — как «забыл».")) return;
        await finishAs("abandon");
        viewAttemptAgain();
      };
      $("#submit", el).onclick = async () => {
        if (!confirm("Сдать решение? Будет финальный прогон тестов и оценка.")) return;
        await ide.saveAll();
        ended = true;
        clearInterval(tick); clearInterval(autosave);
        $("#submit", el).disabled = true;
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
  return `<div class="stepper">${RSTEPS.map(([n, name]) => `<span class="st ${r.status === "active" && r.step === n ? "cur" : (r.status === "passed" || r.step > n) ? "done" : ""}">${r.status === "passed" || r.step > n ? "✓" : n} ${name}</span>`).join('<span class="muted">→</span>')}
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
- \`reference/\` — эталон: файлы, которые вы учите. Запускаются здесь кнопкой «Запустить» (рабочая папка — корень задачи).
- \`starter/\` — заготовки: \`starter/model.py\` подставится в попытку вместо пустого \`model.py\`
- \`tests/test_*.py\` — pytest; импортируют код по имени файла: \`from model import Net\`
- \`data/\` — датасеты (или подключённая папка), \`results/\` — что сохраняет код
- \`task.json\` — название, тип, тема, лимит времени, главный файл, роли

Фикстуры в тестах: \`device\`, \`seed\`, \`data_dir\`.

«Проверить» гоняет тесты на эталоне из папки — так видно, что тесты верные. «Сохранить версию» делает снимок папки: новые попытки пойдут по нему.`)}</div>`; } };
  current = await openIDE(view, {
    title: `${t.title} · редактор задачи`, base, back: `#/task/${id}`, roles: Object.fromEntries(Object.entries(t.roles).map(([f, r]) => [`reference/${f}`, r])),
    open: [t.reference[0] ? `reference/${t.main_file && t.reference.includes(t.main_file) ? t.main_file : t.reference[0]}` : "description.md"],
    preload: t.reference.map(f => `reference/${f}`), pyFiles: t.reference.map(f => `reference/${f}`), expand: ["reference", "tests"],
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
  const st = await api("/api/stats");
  const tasks = (await api("/api/tasks")).filter(t => t.attempts);
  const s = st.streak, maxC = Math.max(1, ...st.calendar.map(d => d.count));
  view.innerHTML = `<h1>Статистика</h1>
    <div class="tiles">
      <div class="tile"><div class="label">Серия</div><div class="num ${s.current ? "ok" : "muted"}">${s.current}</div><div class="muted small">дн. подряд${s.current && !s.today_done ? " · сегодня ещё не решали" : ""}</div></div>
      <div class="tile"><div class="label">Лучшая серия</div><div class="num">${s.best}</div><div class="muted small">дн.</div></div>
      <div class="tile"><div class="label">Сдано попыток</div><div class="num">${st.attempts}</div><div class="muted small">задач: ${st.tasks}</div></div>
      <div class="tile"><div class="label">Активных дней</div><div class="num">${st.days_active}</div><div class="muted small">за всё время</div></div>
    </div>
    <div class="card"><h3>12 недель</h3><div class="cal">${st.calendar.map(d => `<i class="${d.count ? "on" : ""}" style="--a:${d.count ? 0.35 + 0.65 * d.count / maxC : 0}" title="${d.date}: ${d.count}"></i>`).join("")}${'<i class="future"></i>'.repeat((7 - st.calendar.length % 7) % 7)}</div></div>
    <div class="card"><h3>Слабые темы</h3>${st.weak_tags.length ? `<table><thead><tr><th>Тема</th><th>Попыток</th><th>Средняя оценка</th><th>Тесты с ошибками</th></tr></thead><tbody>
      ${st.weak_tags.map(t => `<tr><td>${esc(t.tag)}</td><td class="muted">${t.attempts}</td><td>${t.avg_score ?? "—"}</td>
        <td><span class="bar"><i style="width:${Math.round(t.fail_rate * 100)}%"></i></span> <span class="muted small">${t.fails}/${t.tests}</span></td></tr>`).join("")}</tbody></table>` : '<div class="empty">данных пока нет</div>'}</div>
    <div class="card"><h3>Слабые тесты</h3>${st.weak_tests.length ? `<table><thead><tr><th>Тест</th><th>Задача</th><th>Падал</th><th>Последняя ошибка</th></tr></thead><tbody>
      ${st.weak_tests.map(t => `<tr class="link" data-t="${t.task_id}"><td class="mono small">${esc(t.test)}</td><td>${esc(t.task)}</td><td class="err nowrap">${t.fails} из ${t.n}</td>
        <td class="muted small" title="${esc(t.last_error)}">${esc(t.last_error)}</td></tr>`).join("")}</tbody></table>` : '<div class="empty">ошибок в тестах пока нет</div>'}</div>
    <div class="card"><h3>Прогресс по задаче</h3>${tasks.length ? `<select id="pick">${tasks.map(t => `<option value="${t.id}">${esc(t.title)}</option>`).join("")}</select><div id="prog" class="mt"></div>` : '<div class="empty">сданных попыток нет</div>'}</div>`;
  $$("tr[data-t]").forEach(tr => tr.onclick = () => { location.hash = `#/task/${tr.dataset.t}`; });
  if (tasks.length) {
    const show = async tid => {
      const list = (await api(`/api/tasks/${tid}/attempts`)).filter(a => a.status === "submitted").reverse();
      historyCharts($("#prog"), list.map(a => ({ date: a.finished_at, score: a.score, total_ms: a.total_ms })));
    };
    $("#pick").onchange = e => show(e.target.value);
    show(tasks[0].id);
  }
}

// ---------------- Настройки ----------------
async function viewSettings() {
  const s = await api("/api/settings");
  const num = (k, label, hint = "") => `<div class="row" style="padding:3px 0"><label class="grow">${label}${hint ? ` <span class="muted small">${hint}</span>` : ""}</label><input type="number" min="0" data-k="${k}" value="${s[k]}" style="width:90px"></div>`;
  view.innerHTML = `<h1>Настройки</h1>
    <div class="card"><h3>Оценка</h3>
      <p class="muted small">Оценка = 100 · доля прошедших тестов − штрафы. Уровень повторения: ≥90 легко, ≥70 нормально, ≥50 трудно, иначе забыл.</p>
      ${num("free_checks", "«Проверить» без штрафа, раз")}${num("check_penalty", "Штраф за каждое следующее «Проверить»")}${num("check_penalty_max", "Максимальный штраф за «Проверить»")}
      ${num("ref_penalty", "Штраф за открытый эталон")}${num("time_penalty", "Штраф за время дольше прошлого раза")}${num("slower_pct", "…если дольше больше чем на, %")}</div>
    <div class="card"><h3>LLM-комментарий</h3>
      <label class="row"><input type="checkbox" id="judge" ${+s.llm_judge ? "checked" : ""}> После сдачи — короткий комментарий по стилю и отличиям от эталона (на оценку не влияет)</label>
      <div class="row mt"><label>Провайдер</label><select id="prov"><option value="ollama" ${s.llm_provider === "ollama" ? "selected" : ""}>Ollama (локально)</option><option value="groq" ${s.llm_provider === "groq" ? "selected" : ""}>Groq API</option></select></div>
      <div class="row mt"><label>Ollama URL</label><input id="o-url" class="grow" value="${esc(s.ollama_url)}"><label>модель</label><input id="o-model" value="${esc(s.ollama_model)}"></div>
      <div class="row mt"><label>Groq модель</label><input id="g-model" class="grow" value="${esc(s.groq_model)}"><span class="${s.groq_key_set ? "ok" : "warn"} small">GROQ_API_KEY ${s.groq_key_set ? "задан" : "не задан (.env)"}</span></div>
      <div class="row mt"><button id="test">Проверить связь</button><span id="test-out" class="small"></span></div></div>
    <div class="card" id="map-card"></div>
    <div class="card"><h3>Бэкап</h3>
      <p class="muted small">Экспорт — один .zip: база (задачи, версии, попытки, расписание, настройки) и текстовые файлы задач. Датасеты из data/ в архив не входят.
        Импорт заменяет базу; текущая перед этим сохраняется в data/backups/. Автокопия базы — раз в день, хранятся 7 последних.</p>
      <div class="row"><a class="btn" href="/api/backup/export" download>Экспорт</a><button id="imp">Импорт…</button><input type="file" id="imp-file" accept=".zip" hidden><button id="bk-now" class="ghost">Автокопия сейчас</button></div>
      <div id="bk-list" class="small muted mt mono"></div></div>
    <button class="primary" id="save">Сохранить настройки</button>`;
  const save = () => api("/api/settings", { method: "PUT", json: {
    ...Object.fromEntries($$("[data-k]").map(i => [i.dataset.k, Math.max(0, +i.value || 0)])), llm_judge: $("#judge").checked ? 1 : 0,
    llm_provider: $("#prov").value, ollama_url: $("#o-url").value, ollama_model: $("#o-model").value, groq_model: $("#g-model").value } });
  $("#save").onclick = async () => { await save(); toast("сохранено"); };
  $("#test").onclick = async () => {
    await save();
    $("#test-out").innerHTML = '<span class="muted spinner">спрашиваю модель</span>';
    const r = await api("/api/settings/test", { method: "POST" });
    $("#test-out").innerHTML = r.ok ? `<span class="ok">ok</span> · ${esc(r.provider)} · ${esc(r.model)} · ${(r.ms / 1000).toFixed(1)} с: «${esc(r.answer)}»` : `<span class="err">нет связи: ${esc(r.answer)}</span>`;
  };
  const list = l => { $("#bk-list").innerHTML = l.map(b => `${esc(b.name)} · ${fmtSize(b.size)} · ${fmtDate(b.created)}`).join("<br>") || "копий нет"; };
  mapSettingsCard($("#map-card"));
  api("/api/backup/list").then(list);
  $("#bk-now").onclick = async () => { const r = await api("/api/backup/now", { method: "POST" }); list(r.backups); toast(r.made ? `создана ${r.made}` : "сегодняшняя копия уже есть"); };
  $("#imp").onclick = () => $("#imp-file").click();
  $("#imp-file").onchange = async e => {
    const f = e.target.files[0];
    if (!f || !confirm(`Заменить базу содержимым «${f.name}»?`)) return;
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/backup/import", { method: "POST", body: fd }); toast(`импортировано задач: ${r.tasks}`); api("/api/backup/list").then(list); }
    catch (err) { toast(err.message, true); }
  };
}
