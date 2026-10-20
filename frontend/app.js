// CODE RECALL — экраны: «Сегодня», «Задачи», задача, решение (IDE), статистика, настройки.
const view = $("#view");
let current = null;  // открытая IDE — закрываем при уходе со страницы

$("#theme").onclick = () => setTheme(theme() === "dark" ? "light" : "dark");

const routes = { today: viewToday, tasks: viewTasks, task: viewTask, attempt: viewAttempt, edit: viewEdit,
                 stats: viewStats, settings: viewSettings };
function route() {
  if (current) { current.dispose(); current = null; }
  const [name, ...args] = location.hash.replace(/^#\/?/, "").split("/");
  const nav = { task: "tasks", attempt: "tasks", edit: "tasks" }[name] || name || "today";
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

async function startAttempt(taskId) {
  try {
    const a = await api(`/api/tasks/${taskId}/attempts`, { method: "POST" });
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
      <td><span class="title">${esc(r.title)}</span><div class="muted small">${esc(r.reason)}</div></td>
      <td>${kindBadge(r.kind)}</td><td class="muted">${esc(r.tag || "")}</td>
      <td class="nowrap muted">${r.due_at || ""}</td>
      <td class="nowrap" style="text-align:right"><button class="${cls === "muted" ? "" : "primary"} small" data-go="${r.id}">${r.active_attempt ? "продолжить" : "решать"}</button></td>
    </tr>`).join("")}</tbody></table></div>` : `<div class="empty">${empty}</div>`}</div>`;
  const total = t.overdue.length + t.due.length;
  view.innerHTML = `<div class="row" style="margin-bottom:14px"><h1 style="margin:0">Сегодня</h1>
      <span class="muted">${total ? `к повторению: ${total}` : "повторений на сегодня нет"}${t.new.length ? ` · новых задач: ${t.new.length}` : ""}</span></div>
    ${section(t.overdue, "Просрочено", "err", "ничего не просрочено")}
    ${section(t.due, "На сегодня", "warn", "на сегодня всё повторено")}
    ${section(t.new, "Новые", "muted", 'новых задач нет — <a href="#/tasks">загрузите задачи</a>')}
    ${t.upcoming.length ? section(t.upcoming, "Ближайшие 7 дней", "ok", "") : ""}`;
  $$("[data-go]").forEach(b => b.onclick = e => { e.stopPropagation(); startAttempt(b.dataset.go); });
  $$("tr[data-id]").forEach(tr => tr.onclick = () => { location.hash = `#/task/${tr.dataset.id}`; });
}

// ---------------- Задачи (как список задач LeetCode) ----------------
const lib = { q: "", kind: "", status: "", tag: "", sort: "title", dir: 1 };
async function viewTasks() {
  const tasks = await api("/api/tasks");
  const tags = [...new Set(tasks.map(t => t.tag).filter(Boolean))].sort();
  const cols = [["status", ""], ["title", "Название"], ["kind", "Тип"], ["tag", "Тема"], ["best_score", "Лучшая оценка"], ["attempts", "Попыток"], ["due_at", "Повтор"]];
  view.innerHTML = `
    <div class="row" style="margin-bottom:14px"><h1 style="margin:0">Задачи</h1><span class="muted">${tasks.length}</span><span class="grow"></span>
      <button id="new">＋ Новая задача</button><button class="primary" id="upload">⇪ Загрузить папки</button></div>
    <div class="card">
      <div class="row" style="margin-bottom:10px">
        <input id="q" placeholder="Поиск задач" value="${esc(lib.q)}" style="min-width:220px">
        <select id="f-kind"><option value="">Все типы</option><option value="algo" ${lib.kind === "algo" ? "selected" : ""}>Алгоритм</option><option value="ml" ${lib.kind === "ml" ? "selected" : ""}>ML</option></select>
        <select id="f-status"><option value="">Любой статус</option>${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${lib.status === k ? "selected" : ""}>${v[2]}</option>`).join("")}</select>
        <select id="f-tag"><option value="">Все темы</option>${tags.map(t => `<option ${t === lib.tag ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
      </div>
      <div class="scroll-x"><table><thead><tr>${cols.map(([k, n]) => `<th class="sort" data-k="${k}">${n}${lib.sort === k ? (lib.dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead>
        <tbody id="rows"></tbody></table></div>
      ${tasks.length ? "" : '<div class="empty">Задач пока нет. Перетащите папку задачи (reference/, tests/, description.md) — например из examples/.</div>'}
    </div>`;
  const rank = { due: 0, new: 1, solved: 2 };
  const render = () => {
    const rows = tasks.filter(t => (!lib.kind || t.kind === lib.kind) && (!lib.status || t.status === lib.status) && (!lib.tag || t.tag === lib.tag)
        && (t.title + " " + t.name + " " + t.tag).toLowerCase().includes(lib.q.toLowerCase()))
      .sort((a, b) => {
        let x = a[lib.sort], y = b[lib.sort];
        if (lib.sort === "status") { x = rank[x]; y = rank[y]; }
        if (x == null) return 1; if (y == null) return -1;
        return (typeof x === "string" ? x.localeCompare(y) : x - y) * lib.dir;
      });
    $("#rows").innerHTML = rows.map(t => `<tr class="link" data-id="${t.id}">
      <td style="width:28px">${statusCell(t.status)}</td>
      <td><span class="title">${esc(t.title)}</span>${t.active_attempt ? ' <span class="badge warn">в процессе</span>' : ""}</td>
      <td>${kindBadge(t.kind)}</td><td class="muted">${esc(t.tag || "—")}</td>
      <td>${t.best_score != null ? `<span class="${t.best_score >= 70 ? "ok" : t.best_score >= 50 ? "warn" : "err"}">${t.best_score}</span>` : '<span class="muted">—</span>'}</td>
      <td class="muted">${t.attempts}</td><td class="muted nowrap">${t.due_at ? t.due_at.slice(0, 10) : "—"}</td></tr>`).join("")
      || '<tr><td colspan="7" class="empty">ничего не найдено</td></tr>';
  };
  render();
  $("#q").oninput = e => { lib.q = e.target.value; render(); };
  $("#f-kind").onchange = e => { lib.kind = e.target.value; render(); };
  $("#f-status").onchange = e => { lib.status = e.target.value; render(); };
  $("#f-tag").onchange = e => { lib.tag = e.target.value; render(); };
  $$("th.sort").forEach(th => th.onclick = () => { lib.dir = lib.sort === th.dataset.k ? -lib.dir : 1; lib.sort = th.dataset.k; viewTasks(); });
  $("#rows").onclick = e => { const tr = e.target.closest("tr[data-id]"); if (tr) location.hash = `#/task/${tr.dataset.id}`; };
  $("#upload").onclick = uploadDialog;
  $("#new").onclick = async () => {
    const title = prompt("Название задачи");
    if (!title) return;
    const kind = confirm("Это ML-задача (данные, модели)? ОК — ML, Отмена — алгоритм") ? "ml" : "algo";
    try { const r = await api("/api/tasks", { method: "POST", json: { title, kind } }); location.hash = `#/edit/${r.id}`; }
    catch (e) { toast(e.message, true); }
  };
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
    const lbl = { new: ["ok", "новая"], changed: ["warn", "новая версия"], unchanged: ["muted", "без изменений"], error: ["err", "ошибка"] };
    pv.innerHTML = res.map(r => `<div class="card" style="box-shadow:none;border:1px solid var(--line);margin-bottom:8px">
        <div class="row"><span class="badge ${lbl[r.status][0]}">${lbl[r.status][1]}</span><b>${esc(r.folder)}</b>
          ${r.version ? `<span class="muted small">v${r.version}${r.status === "changed" ? ` → v${r.version + 1}` : ""}</span>` : ""}
          ${r.data_files ? `<span class="muted small">+ ${r.data_files} файлов в data/</span>` : ""}</div>
        ${r.error ? `<div class="err small mt">${esc(r.error)}</div>` : ""}
        ${r.files ? `<div class="muted small mt">${r.files.map(esc).join(" · ")}</div>` : ""}
        ${r.status === "changed" ? `<div class="small mt">${r.added.length ? `<span class="ok">+ ${r.added.map(esc).join(", ")}</span><br>` : ""}${r.removed.length ? `<span class="err">− ${r.removed.map(esc).join(", ")}</span><br>` : ""}
          ${r.changed.map(f => `<details><summary>изменён ${esc(f)}</summary><div class="diff">${diffHtml(r.diff[f])}</div></details>`).join("")}</div>` : ""}
      </div>`).join("") + `<div class="row mt"><span class="grow"></span><button data-x>Отмена</button>
        <button class="primary" id="save" ${res.some(r => r.status === "new" || r.status === "changed") ? "" : "disabled"}>Сохранить</button></div>`;
    $$("[data-x]", back).forEach(b => b.onclick = close);
    $("#save", back).onclick = async () => {
      try {
        const out = await api("/api/tasks/upload", { method: "POST", body: form(items) });
        toast(out.map(o => `${o.folder}: ${{ created: "создана", new_version: `версия ${o.version}`, unchanged: "без изменений" }[o.status] || o.error}`).join(" · "));
        close(); viewTasks();
      } catch (e) { toast(e.message, true); }
    };
  }
}

// ---------------- Страница задачи ----------------
async function viewTask(id, tab = "about") {
  const t = await api(`/api/tasks/${id}`);
  view.innerHTML = `
    <div class="row" style="margin-bottom:6px"><a href="#/tasks" class="muted">← Задачи</a></div>
    <div class="row" style="margin-bottom:14px"><h1 style="margin:0">${esc(t.title)}</h1>${kindBadge(t.kind)}${t.tag ? `<span class="badge">${esc(t.tag)}</span>` : ""}
      ${statusCell(t.status)}<span class="grow"></span>
      <a class="btn" href="#/edit/${t.id}">✎ Редактировать задачу</a>
      <button class="primary" id="go">${t.active_attempt ? "Продолжить решение" : "Решать"}</button></div>
    <div class="tabs">${[["about", "Описание"], ["attempts", "Попытки"], ["versions", "Версии"], ["settings", "Настройки"]]
      .map(([k, n]) => `<a href="#/task/${id}/${k}" class="${k === tab ? "active" : ""}">${n}</a>`).join("")}</div>
    <div id="tab"></div>`;
  $("#go").onclick = () => startAttempt(t.id);
  const box = $("#tab");
  if (tab === "about") {
    box.innerHTML = `<div class="card"><div class="md">${t.description ? md(t.description) : '<p class="muted">Описания нет — добавьте description.md в редакторе задачи.</p>'}</div></div>
      <div class="card"><div class="row"><span class="label" style="margin:0">Файлы эталона</span></div>
        <div class="mt">${t.reference.map(f => `<span class="badge">${esc(f)} · ${t.roles[f] === "given" ? "дан" : "пишу сам"}</span>`).join(" ")}</div>
        <div class="muted small mt">тестов: ${t.test_files.map(esc).join(", ") || "нет"} · лимит времени ${t.timeout} с · версия ${t.version}${t.dirty ? ' · <span class="warn">в папке есть несохранённые изменения</span>' : ""}</div></div>`;
  } else if (tab === "attempts") {
    const list = await api(`/api/tasks/${id}/attempts`);
    const done = list.filter(a => a.status === "submitted").reverse();
    box.innerHTML = `<div class="card">${list.length ? `<div class="scroll-x"><table><thead><tr><th>Дата</th><th>Статус</th><th>Оценка</th><th>Время</th><th>Уровень</th><th>«Проверить»</th></tr></thead><tbody>
      ${list.map(a => `<tr class="link" data-a="${a.id}"><td class="nowrap">${fmtDate(a.started_at)}</td>
        <td>${{ active: '<span class="badge warn">в процессе</span>', checking: '<span class="badge warn">проверяется</span>', submitted: '<span class="badge ok">сдано</span>', abandoned: '<span class="badge">брошено</span>' }[a.status]}</td>
        <td>${a.score ?? "—"}</td><td class="mono">${fmtMs(a.total_ms)}</td>
        <td class="${GRADE_CLS[a.grade] || "muted"}">${a.grade ?? "—"}${a.grade_manual ? " ✎" : ""}</td><td class="muted">${a.checks}${a.ref_opened ? " · эталон открыт" : ""}</td></tr>`).join("")}
      </tbody></table></div>` : '<div class="empty">попыток ещё не было</div>'}</div>
      ${done.length ? '<div class="card"><h3>Оценка и время по попыткам</h3><div id="hist"></div></div>' : ""}`;
    $$("tr[data-a]", box).forEach(tr => tr.onclick = () => { location.hash = `#/attempt/${tr.dataset.a}`; });
    if (done.length) historyCharts($("#hist"), done.map(a => ({ date: a.finished_at, score: a.score, total_ms: a.total_ms })));
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
        <label>Тема</label><input id="s-tag" value="${esc(t.tag)}" placeholder="сортировка, pandas…"></div>
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
    try { await api(`/api/tasks/${t.id}`, { method: "PATCH", json: { title: $("#s-title").value, kind: $("#s-kind").value, tag: $("#s-tag").value.trim(), timeout: +$("#s-timeout").value } }); toast("сохранено"); }
    catch (e) { toast(e.message, true); }
  };
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

// ---------------- Решение (IDE) ----------------
async function viewAttempt(id) {
  let a = await api(`/api/attempts/${id}`);
  const readonly = a.status !== "active";
  const base = `/api/attempts/${id}`;
  const loadedAt = Date.now(), baseMs = a.total_ms;
  const totalMs = () => readonly ? a.total_ms : baseMs + (Date.now() - loadedAt);
  const written = Object.entries(a.roles).filter(([, r]) => r === "write").map(([f]) => f);
  let refFiles = null;
  const diffs = readonly && a.report?.diffs ? await api(`${base}/reference`, { method: "POST" }).then(r => { refFiles = r.files; return Object.fromEntries(written.map(f => [f, r.files[f] || ""])); }) : null;

  const leftTabs = [
    { id: "desc", label: "Описание", render: el => { el.innerHTML = `<h2>${esc(a.title)}</h2><div class="row" style="margin-bottom:10px">${kindBadge(a.kind)}${a.tag ? `<span class="badge">${esc(a.tag)}</span>` : ""}
        <span class="muted small">v${a.version} · лимит ${a.timeout} с</span></div>
      <div class="md">${a.description ? md(a.description) : '<p class="muted">описания нет</p>'}</div>
      <div class="label mt">Файлы</div>${a.files.map(f => `<div class="small"><span class="mono">${esc(f)}</span> — ${a.roles[f] === "given" ? "дан" : "пишу сам"}</div>`).join("")}`; } },
    ...(readonly && a.report ? [{ id: "report", label: "Отчёт", render: el => renderReport(el, a, (na) => { a = na; }) }] : []),
    { id: "attempts", label: "Попытки", render: async el => {
      const list = await api(`/api/tasks/${a.task_id}/attempts`);
      const done = list.filter(x => x.status === "submitted").reverse();
      el.innerHTML = `${list.map(x => `<div class="row small" style="padding:4px 0;border-bottom:1px solid var(--line)"><a href="#/attempt/${x.id}">${fmtDate(x.started_at)}</a>
          <span class="grow"></span>${x.score != null ? `<b>${x.score}</b>` : `<span class="muted">${x.status === "active" ? "в процессе" : "—"}</span>`}<span class="mono muted">${fmtMs(x.total_ms)}</span></div>`).join("")}
        ${done.length ? '<div id="h" class="mt"></div>' : ""}`;
      if (done.length) historyCharts($("#h", el), done.map(x => ({ date: x.finished_at, score: x.score, total_ms: x.total_ms })));
    } },
    { id: "ref", label: "Эталон", render: el => renderReference(el, a, base, readonly, () => refFiles, f => { refFiles = f; a.ref_opened = true; }) },
  ];

  current = await openIDE(view, {
    title: a.title + (readonly ? " · сдано" : ""), base, readonly, back: `#/task/${a.task_id}`,
    roles: a.roles, main: a.main_file, pyFiles: a.files, preload: a.files, expand: [],
    open: readonly ? written.filter(f => diffs && f in diffs) : [a.main_file, ...a.files.filter(f => a.roles[f] === "write" && f !== a.main_file)].filter(Boolean),
    diffs, dataLink: a.data_link,
    leftTabs, leftTab: readonly && a.report ? "report" : "desc",
    run: path => api(`${base}/run`, { method: "POST", json: { path } }).then(r => r.job),
    exec: code => api(`${base}/exec`, { method: "POST", json: { code } }).then(r => r.job),
    stop: () => api(`${base}/stop`, { method: "POST" }),
    check: () => api(`${base}/check`, { method: "POST" }).then(r => { a.checks = r.checks; updateChecks(); return r.job; }),
    bindData: ide => bindDataPrompt(a.task_id, ide),
    buttons: (el, ide) => {
      el.innerHTML = `<span class="timer" id="timer" title="время попытки">${fmtMs(totalMs())}</span>
        ${readonly ? `<span class="badge ok">сдано</span>${a.score != null ? `<b>${a.score}</b>` : ""}`
          : `<span class="muted small" id="checks"></span><button class="ghost" id="reset" title="вернуть заготовку текущего файла">↺ Сбросить файл</button>
             <button class="ghost" id="abandon" title="бросить попытку">Бросить</button><button class="primary" id="submit">Сдать</button>`}`;
      if (readonly) return;
      $("#reset", el).onclick = async () => {
        const p = ide.current;
        if (!p || !(p in a.roles)) return toast("откройте файл задачи", true);
        if (!confirm(`Вернуть ${p} к заготовке? Текущий код пропадёт.`)) return;
        const r = await api(`${base}/reset`, { method: "POST", json: { path: p } });
        ide.models[p].setValue(r.content);
        await ide.save(p);
      };
      $("#abandon", el).onclick = async () => {
        if (!confirm("Бросить попытку? Она останется в истории как брошенная.")) return;
        await saveTime(); await api(`${base}/abandon`, { method: "POST" }); location.hash = `#/task/${a.task_id}`;
      };
      $("#submit", el).onclick = async () => {
        if (!confirm("Сдать решение? Будет финальный прогон тестов и оценка.")) return;
        await ide.saveAll();
        clearInterval(tick); clearInterval(autosave);
        $("#submit", el).disabled = true;
        ide.showConsole("tests");
        const tv = $('[data-cv="tests"]', view);
        tv.innerHTML = '<div class="run-head"><span>финальный прогон</span><span class="spinner"></span></div><div data-o></div>';
        const { job } = await api(`${base}/submit`, { method: "POST", json: { total_ms: totalMs() } });
        await followJob(job, outs => renderOutputs($("[data-o]", tv), outs, ide.rawUrl));
        viewAttempt(id);
      };
    },
  });
  const ide = current;
  function updateChecks() { const c = $("#checks"); if (c) c.textContent = a.checks ? `«Проверить»: ${a.checks}` : ""; }
  updateChecks();
  if (readonly && a.report?.result) ide.showTests(a.report.result);
  const saveTime = () => readonly ? null : fetch(`${base}/time`, { method: "PUT", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ total_ms: Math.round(totalMs()) }) }).catch(() => {});
  const tick = setInterval(() => { const t = $("#timer"); if (!t) return clearInterval(tick); t.textContent = fmtMs(totalMs()); }, 1000);
  const autosave = readonly ? null : setInterval(saveTime, 15000);
  const dispose = ide.dispose;
  ide.dispose = () => { clearInterval(tick); clearInterval(autosave); saveTime(); dispose(); };
  window.addEventListener("beforeunload", saveTime, { once: true });
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
      el.innerHTML = `<span class="muted small">v${t.version}</span><button class="primary" id="save-v" title="снимок папки: description, reference, starter, tests">Сохранить версию</button>`;
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
