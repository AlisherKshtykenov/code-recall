// «Карта навыков»: строки — типы задач, столбцы — категории, в ячейках — кирпичики-чипы.

const CHIP = { planned: ["planned", "запланировано — задачи ещё нет"], new: ["new", "новая — ещё не решал"],
               learned: ["learned", "выучено"], due: ["due", "пора повторить"], weak: ["weak", "слабо: прошлый раз ошибся или сломано зависимостью"],
               concept: ["concept", "концепт — только README"] };
const mapState = { sort: "reuse", dir: -1 };

async function viewMap(focus) {
  const m = await api("/api/map");
  const rows = arr(m.rows), cats = arr(m.categories), B = m.bricks || {};
  if (!rows.length) {
    view.innerHTML = `<h1>Карта навыков</h1><div class="card empty">Карта пуста. Загрузите combinations.csv в <a href="#/settings">Настройках</a> → «Карта навыков».</div>`;
    return;
  }
  const cov = m.coverage || { total: 0, created: 0, learned: 0, concepts: 0 };
  const pct = (a, b) => b ? Math.round(100 * a / b) : 0;
  const chip = name => {
    const b = B[name] || { status: "planned", kind: "brick" }, [cls, tip] = CHIP[b.status] || CHIP.planned;
    const st = b.statuses || {};
    const split = b.task_id && b.kind !== "concept";  // у созданной задачи — две половинки: библиотека | с нуля
    const halves = split ? MODES.map(m => `${MODE_TITLE[m]}: ${(CHIP[st[m]] || ["", st[m] === "none" ? "нет режима" : "—"])[1].split(" — ")[0]}`).join(" · ") : tip;
    return `<button class="chip ${split ? "split" : cls}" data-chip="${esc(name)}" ${split ? `style="--l: var(--chip-${st.library || "none"}); --r: var(--chip-${st.scratch || "none"})"` : ""}
      title="${esc(name)} — ${esc(halves)}${b.note ? ` · ${esc(b.note)}` : ""} · в ${b.reuse || 0} строках">${esc(name)}</button>`;
  };
  const cell = items => {
    const groups = [];
    arr(items).forEach(it => {  // «a / b» — варианты одного слота, рисуем рядом через «/»
      const g = it.slot_group != null ? groups.find(x => x.sg === it.slot_group) : null;
      g ? g.names.push(it.name) : groups.push({ sg: it.slot_group, names: [it.name], together: it.together });
    });
    return groups.map(g => g.names.map(chip).join('<span class="muted small"> / </span>')).join(" ") || '<span class="muted small">—</span>';
  };
  const list = Object.values(B).filter(b => b.kind !== "concept");
  view.innerHTML = `<div class="row" style="margin-bottom:12px"><h1 style="margin:0">Карта навыков</h1><span class="grow"></span>
      <span class="legend"><span class="chip split" style="--l: var(--chip-learned); --r: var(--chip-new)" title="слева — «Библиотека», справа — «С нуля»">библиотека | с нуля</span>${Object.entries(CHIP).map(([k, [c, t]]) => `<span class="chip ${c}" title="${t}">${{ planned: "запланировано", new: "новая", learned: "выучено", due: "повторить", weak: "слабо", concept: "концепт" }[k]}</span>`).join("")}</span></div>
    <div class="tiles">
      <div class="tile"><div class="label">Кирпичиков на карте</div><div class="num">${cov.total}</div><div class="muted small">+ концептов: ${cov.concepts}</div></div>
      <div class="tile"><div class="label">Создано задач</div><div class="num">${cov.created}</div><div class="bar"><i style="width:${pct(cov.created, cov.total)}%"></i></div><div class="muted small">${pct(cov.created, cov.total)}%</div></div>
      <div class="tile"><div class="label">Выучено</div><div class="num ok">${cov.learned}</div><div class="bar"><i class="ok" style="width:${pct(cov.learned, cov.total)}%"></i></div><div class="muted small">${pct(cov.learned, cov.total)}%</div></div>
    </div>
    <div class="card"><p class="muted small" style="margin-top:0">Наведите на кирпичик — подсветятся все строки, где он используется. Клик — к задаче (у запланированных — создать задачу).</p>
      <div class="scroll-x"><table class="map"><thead><tr><th>Задача</th>${cats.map(c => `<th>${esc(c.title)}${c.slot ? `<div class="muted small">слот ${esc(c.slot)}</div>` : ""}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(r => `<tr data-row="${esc(r.key)}" data-bricks="${esc(Object.values(r.cells || {}).flat().map(i => i.name).join(" "))}">
        <td class="nowrap"><a href="#/tasks" data-topic="${r.topic_id ?? ""}"><b>${esc(r.title)}</b></a></td>${cats.map(c => `<td>${cell((r.cells || {})[c.key])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>
    <div class="card"><h3>Что учить первым</h3><p class="muted small">Кирпичики, которые повторно используются в большем числе строк карты, окупаются быстрее всего.</p>
      <div class="scroll-x"><table><thead><tr>${[["name", "Кирпичик"], ["cat", "Категория"], ["reuse", "Используется в N задачах"], ["status", "Статус"]]
        .map(([k, n]) => `<th class="sort" data-s="${k}">${n}${mapState.sort === k ? (mapState.dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead><tbody id="reuse"></tbody></table></div></div>`;
  const catTitle = Object.fromEntries(cats.map(c => [c.key, c.title]));
  const rank = { weak: 0, due: 1, new: 2, planned: 3, learned: 4 };
  const renderReuse = () => {
    const key = b => mapState.sort === "cat" ? catTitle[b.categories[0]] || "" : mapState.sort === "status" ? rank[b.status] : mapState.sort === "name" ? b.name : b.reuse;
    const sorted = [...list].sort((a, b) => { const x = key(a), y = key(b); return (typeof x === "string" ? x.localeCompare(y) : x - y) * mapState.dir || b.reuse - a.reuse || a.name.localeCompare(b.name); });
    $("#reuse").innerHTML = sorted.map(b => `<tr data-bricks="${esc(b.name)}"><td>${chip(b.name)}</td><td class="muted small">${arr(b.categories).map(c => esc(catTitle[c] || c)).join(", ")}</td>
      <td><b>${b.reuse}</b></td><td class="small">${(CHIP[b.status] || CHIP.planned)[1].split(" — ")[0]}</td></tr>`).join("");
    bindChips();
  };
  $$("th[data-s]").forEach(th => th.onclick = () => { mapState.dir = mapState.sort === th.dataset.s ? -mapState.dir : (th.dataset.s === "reuse" ? -1 : 1); mapState.sort = th.dataset.s; viewMap(); });
  $$("a[data-topic]").forEach(a => a.onclick = () => { lib.topic = a.dataset.topic ? +a.dataset.topic : null; store.set("lib.topic", lib.topic); });
  // наведение: все строки матрицы, где есть кирпичик, и все его чипы
  const light = (name, on) => {
    $$("table.map tr[data-bricks]").forEach(tr => tr.classList.toggle("hl", on && tr.dataset.bricks.split(" ").includes(name)));
    $$(`[data-chip="${CSS.escape(name)}"]`).forEach(c => c.classList.toggle("hl", on));
  };
  function bindChips() {
    $$("[data-chip]").forEach(c => {
      c.onmouseenter = () => light(c.dataset.chip, true);
      c.onmouseleave = () => light(c.dataset.chip, false);
      c.onclick = () => openChip(B[c.dataset.chip] || { name: c.dataset.chip, status: "planned" });
    });
  }
  renderReuse();
  if (focus && B[focus]) { light(focus, true); $(`[data-chip="${CSS.escape(focus)}"]`)?.scrollIntoView({ block: "center" }); }
}

function openChip(b) {
  if (b.task_id) { location.hash = `#/task/${b.task_id}`; return; }
  if (b.kind === "concept") return toast(`«${b.name}» — концепт: только README, без эталона и тестов${b.note ? ` (${b.note})` : ""}`);
  if (confirm(`Задачи «${b.name}» ещё нет. Создать её в мастере?`)) wizardDialog({ title: b.name, topic_id: b.topic_id });
}

// Карточка в «Настройках»: импорт / переимпорт CSV (новые строки и кирпичики добавляются, задачи не трогаются)
function mapSettingsCard(box) {
  box.innerHTML = `<h3>Карта навыков</h3>
    <p class="muted small">CSV: первая строка — <span class="mono">задача,модели,preprocessing,layers,activations,losses,optimizers,metrics,comparison</span>.
      Повторный импорт добавляет новые строки и кирпичики; существующие задачи и узлы, которые вы перенесли, не меняются.</p>
    <div class="row"><input type="file" id="map-csv" accept=".csv,text/csv"><button id="map-imp" class="primary" disabled>Импортировать</button><a href="#/map">Открыть карту</a></div>
    <div id="map-pv" class="small mt"></div>`;
  const inp = $("#map-csv", box), btn = $("#map-imp", box), pv = $("#map-pv", box);
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
