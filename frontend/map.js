// «Карта навыков»: строки — типы задач, столбцы — категории, в ячейках — кирпичики-чипы.

const CHIP = { planned: ["planned", "запланировано — задачи ещё нет"], new: ["new", "новая — ещё не решал"],
               learned: ["learned", "выучено"], due: ["due", "пора повторить"], weak: ["weak", "слабо: прошлый раз ошибся или сломано зависимостью"],
               concept: ["concept", "концепт — только README"] };
const mapState = { sort: "reuse", dir: -1 };

async function viewMap(focus) {
  const m = await api("/api/map");
  const rows = arr(m.rows), cats = arr(m.categories), B = m.bricks || {};
  if (!rows.length) {
    view.innerHTML = `<h1>Карта навыков</h1><div class="card">${emptyState({ icon: "blocks", title: "Карта пуста", text: "Загрузите combinations.csv — появятся типы задач и нужные им кирпичики.",
      actions: '<a class="btn primary" href="#/settings">Импорт карты навыков</a>' })}</div>`;
    return;
  }
  const cov = m.coverage || { total: 0, created: 0, learned: 0, concepts: 0 };
  const list = Object.values(B).filter(b => b.kind !== "concept");
  const learnedIn = mode => list.filter(b => b.task_id && (b.statuses || {})[mode] === "learned").length;
  const pct = (a, b) => b ? Math.round(100 * a / b) : 0;
  // чип: имя + две иконки режимов со статусом; у запланированных — бледный
  const chip = name => {
    const b = B[name] || { status: "planned", kind: "brick" };
    const real = b.task_id && b.kind !== "concept";
    const st = real ? b.statuses || {} : { library: b.kind === "concept" ? "concept" : "planned", scratch: b.kind === "concept" ? "concept" : "planned" };
    const tip = MODES.map(md => `${MODE_TITLE[md]}: ${(CHIP[st[md]] || ["", st[md] === "none" ? "нет режима" : "—"])[1].split(" — ")[0]}`).join(" · ");
    return `<button class="mchip ${real ? "" : "ghost-chip"} ${b.kind === "concept" ? "concept" : ""}" data-chip="${esc(name)}" title="${esc(name)} — ${esc(tip)}${b.note ? ` · ${esc(b.note)}` : ""}">
      <span class="mc-name">${esc(name)}</span>${modeHalves(st)}</button>`;
  };
  const cell = items => {
    const groups = [];
    arr(items).forEach(it => {  // «a / b» — варианты одного слота
      const g = it.slot_group != null ? groups.find(x => x.sg === it.slot_group) : null;
      g ? g.names.push(it.name) : groups.push({ sg: it.slot_group, names: [it.name] });
    });
    return groups.map(g => g.names.map(chip).join("")).join("");
  };
  const rowStat = r => {
    const names = [...new Set(Object.values(r.cells || {}).flat().map(i => i.name))].filter(n => B[n]?.kind !== "concept");
    const both = names.filter(n => { const s = B[n]?.statuses || {}; return B[n]?.task_id && MODES.every(md => s[md] === "learned" || s[md] === "none"); }).length;
    return `${both} из ${names.length} — оба режима`;
  };
  view.innerHTML = `<div class="map-page">
    <div class="row page-head"><div><h1>Карта навыков</h1><div class="muted">Какие кирпичики нужны каждому типу задач. У чипа две половинки: применение и устройство.</div></div>
      <span class="grow"></span>
      <div class="cov-card"><div><div class="faint small">создано</div><div><b class="num">${cov.created}</b> <span class="muted">из ${cov.total}</span></div></div>
        ${MODES.map(md => `<div class="cov-m">${modeBadge(md, { short: true })}<span class="grow"></span><span>${learnedIn(md)} выучено</span>
          <div class="mc-bar"><i style="width:${pct(learnedIn(md), cov.total)}%;background:var(--ok)"></i></div></div>`).join("")}</div></div>
    <div class="row legend-row"><span class="muted">статусы:</span><span class="badge dot ok">выучено</span><span class="badge dot warn">пора повторить</span><span class="badge dot err">слабо</span>
      <span class="badge dot new">новое</span><span class="badge plan">○ запланировано</span>
      <span class="muted">у чипа слева</span><span class="mi mi-lib">${ICON.book}</span><span class="muted">библиотека, справа</span><span class="mi mi-scr">${ICON.gear}</span><span class="muted">с нуля</span></div>
    <div class="card map-card"><div class="scroll-x"><table class="map"><thead><tr><th>тип задачи</th>${cats.map(c => `<th><span class="cat ${catClass(c.key)}"><i></i>${esc(c.title)}</span>${c.slot ? `<div class="faint small">слот ${esc(c.slot)}</div>` : ""}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(r => `<tr data-row="${esc(r.key)}" data-bricks="${esc(Object.values(r.cells || {}).flat().map(i => i.name).join(" "))}">
        <td class="nowrap"><a href="#/tasks" data-topic="${r.topic_id ?? ""}" class="mono row-title">${esc(r.title)}</a><div class="faint small">${rowStat(r)}</div></td>
        ${cats.map(c => `<td><div class="cell">${cell((r.cells || {})[c.key])}</div></td>`).join("")}</tr>`).join("")}</tbody></table></div></div>
    <div class="map-plate card" id="plate" hidden></div>
    <div class="card"><h3>Что учить первым</h3><p class="muted small">Кирпичики, которые повторно используются в большем числе строк карты, окупаются быстрее всего.</p>
      <div class="scroll-x"><table><thead><tr>${[["name", "Кирпичик"], ["cat", "Категория"], ["reuse", "Используется в N задачах"], ["status", "Статус"]]
        .map(([k, n]) => `<th class="sort" data-s="${k}">${n}${mapState.sort === k ? (mapState.dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead><tbody id="reuse"></tbody></table></div></div></div>`;
  const catTitle = Object.fromEntries(cats.map(c => [c.key, c.title]));
  const rank = { weak: 0, due: 1, new: 2, planned: 3, learned: 4 };
  const renderReuse = () => {
    const key = b => mapState.sort === "cat" ? catTitle[b.categories[0]] || "" : mapState.sort === "status" ? rank[b.status] : mapState.sort === "name" ? b.name : b.reuse;
    const sorted = [...list].sort((a, b) => { const x = key(a), y = key(b); return (typeof x === "string" ? x.localeCompare(y) : x - y) * mapState.dir || b.reuse - a.reuse || a.name.localeCompare(b.name); });
    $("#reuse").innerHTML = sorted.map(b => `<tr data-bricks="${esc(b.name)}"><td>${chip(b.name)}</td><td>${arr(b.categories).map(c => catTag(c, catTitle[c] || c)).join(" ")}</td>
      <td><b>${b.reuse}</b></td><td class="small">${(CHIP[b.status] || CHIP.planned)[1].split(" — ")[0]}</td></tr>`).join("");
    bindChips();
  };
  $$("th[data-s]").forEach(th => th.onclick = () => { mapState.dir = mapState.sort === th.dataset.s ? -mapState.dir : (th.dataset.s === "reuse" ? -1 : 1); mapState.sort = th.dataset.s; viewMap(); });
  $$("a[data-topic]").forEach(a => a.onclick = () => { lib.topic = a.dataset.topic ? +a.dataset.topic : null; store.set("lib.topic", lib.topic); });
  // наведение и выбор: подсвечены строки, где кирпичик нужен, и все его чипы; внизу — плашка выбранного
  let picked = null;
  const light = (name, on, cls = "hl") => {
    $$("table.map tr[data-bricks]").forEach(tr => tr.classList.toggle(cls, on && tr.dataset.bricks.split(" ").includes(name)));
    $$(`[data-chip="${CSS.escape(name)}"]`).forEach(c => c.classList.toggle(cls, on));
  };
  const pick = name => {
    if (picked) light(picked, false, "picked");
    picked = name;
    light(name, true, "picked");
    const b = B[name] || { name, status: "planned" }, st = b.statuses || {};
    const where = rows.filter(r => Object.values(r.cells || {}).flat().some(i => i.name === name)).map(r => r.title);
    const plate = $("#plate");
    plate.hidden = false;
    plate.innerHTML = `<b class="mono">${esc(name)}</b>${b.task_id ? `<span class="mpair">${MODES.map(md => `<span class="mp ${MS_CLS[st[md]] || "none"}">${MODE_NAME[md]} · ${(CHIP[st[md]] || ["", "нет режима"])[1].split(" — ")[0]}</span>`).join("")}</span>`
      : `<span class="badge plan">${b.kind === "concept" ? "концепт" : "запланировано"}</span>`}
      <span class="muted">нужен в ${where.length} ${plural(where.length, "типе", "типах", "типах")} задач: ${where.map(esc).join(", ")}</span><span class="grow"></span>
      <button id="plate-open">${b.task_id ? "Открыть задачу" : b.kind === "concept" ? "Что это" : "Создать задачу"}</button>`;
    $("#plate-open").onclick = () => openChip(b.task_id || b.kind ? b : { name, status: "planned" });
  };
  function bindChips() {
    $$("[data-chip]").forEach(c => {
      c.onmouseenter = () => light(c.dataset.chip, true);
      c.onmouseleave = () => light(c.dataset.chip, false);
      c.onclick = () => pick(c.dataset.chip);
      c.ondblclick = () => openChip(B[c.dataset.chip] || { name: c.dataset.chip, status: "planned" });
    });
  }
  renderReuse();
  if (focus && B[focus]) { pick(focus); $(`[data-chip="${CSS.escape(focus)}"]`)?.scrollIntoView({ block: "center" }); }
}

function openChip(b) {
  if (b.task_id) { location.hash = `#/task/${b.task_id}`; return; }
  if (b.kind === "concept") return toast(`«${b.name}» — концепт: только README, без эталона и тестов${b.note ? ` (${b.note})` : ""}`);
  if (confirm(`Задачи «${b.name}» ещё нет. Создать её в мастере?`)) wizardDialog({ title: b.name, topic_id: b.topic_id });
}

// Карточка в «Настройках»: импорт / переимпорт CSV (новые строки и кирпичики добавляются, задачи не трогаются)
function mapSettingsCard(box) {
  box.innerHTML = `<div class="row"><h2 style="margin:0">Импорт карты навыков</h2><span class="faint mono small">combinations.csv</span><span class="grow"></span><a href="#/map" class="small">Открыть карту</a></div>
    <label class="drop mt" id="map-drop">Перетащи <span class="mono">combinations.csv</span> — какие кирпичики нужны каждому типу задач.<input type="file" id="map-csv" accept=".csv,text/csv" hidden></label>
    <div class="fmt mt"><div class="faint small" style="padding:6px 10px">ожидаемый формат — строка на тип задачи, в ячейке кирпичики через запятую (в кавычках); пояснения в скобках, «нет» — пусто</div>
      <table class="dp"><tr><th>задача</th><th>модели</th><th>preprocessing</th><th>layers</th><th>…</th><th>metrics</th><th>comparison</th></tr>
        <tr><td>regression</td><td>"linear_regression, ridge, lasso"</td><td>"scaling, missing, encoding"</td><td>dense (1 слой)</td><td>…</td><td>"mae, rmse, r2"</td><td>"cross_validation, dummy_mean"</td></tr>
        <tr><td>regression (деревья)</td><td>"decision_tree, random_forest"</td><td>"missing, encoding"</td><td>нет</td><td>…</td><td>"mae, rmse, r2"</td><td>"cross_validation, grid_search"</td></tr></table></div>
    <div class="row mt"><button id="map-imp" class="primary" disabled>Импортировать</button><span class="faint small">Повторный импорт добавляет новые строки и кирпичики; существующие задачи не меняются.</span></div>
    <div id="map-pv" class="small mt"></div>`;
  const inp = $("#map-csv", box), btn = $("#map-imp", box), pv = $("#map-pv", box);
  const dz = $("#map-drop", box);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); inp.files = e.dataTransfer.files; inp.onchange(); };
  const form = () => { const fd = new FormData(); fd.append("file", inp.files[0]); return fd; };
  inp.onchange = async () => {
    btn.disabled = true;
    if (!inp.files[0]) return;
    try {
      const r = await api("/api/map/preview", { method: "POST", body: form() });
      pv.innerHTML = `строк: ${r.rows} (новых ${arr(r.rows_new).length}${arr(r.rows_new).length ? `: ${arr(r.rows_new).map(esc).join(", ")}` : ""}) · кирпичиков: ${r.bricks} (новых ${arr(r.bricks_new).length})`;
      btn.disabled = false;
    } catch (e) { pv.innerHTML = `<span class="err">${esc(e.message)}</span>`; }
  };
  btn.onclick = async () => {
    try {
      const r = await api("/api/map/import", { method: "POST", body: form() });
      pv.innerHTML = `<span class="ok">готово</span>: строк новых ${r.rows_new}, обновлено ${r.rows_updated}; кирпичиков новых ${r.bricks_new}, всего ${r.bricks}`;
    } catch (e) { pv.innerHTML = `<span class="err">${esc(e.message)}</span>`; }
  };
}
