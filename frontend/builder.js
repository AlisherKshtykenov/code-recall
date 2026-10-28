// Конструктор задач — визуальная доска на Drawflow: палитра слева, холст в центре, инспектор справа.
// Стрелка от кирпичика к тому, кто его использует, = зависимость. Тот же холст — «только просмотр»
// во вкладке «Состав» и на экране сборки.

const DRAWFLOW_JS = "https://cdn.jsdelivr.net/npm/drawflow@0.0.60/dist/drawflow.min.js";
const DRAWFLOW_CSS = "https://cdn.jsdelivr.net/npm/drawflow@0.0.60/dist/drawflow.min.css";
const CAT_COLOR = { metrics: "#3b82f6", preprocessing: "#14b8a6", layers: "#a855f7", activations: "#ec4899", losses: "#f97316",
                    optimizers: "#eab308", models: "#22c55e", comparison: "#06b6d4" };
const LEVEL_NAME = { brick: "кирпичик", block: "блок", wall: "стена" };
let drawflowReady = null;

function loadDrawflow() {
  if (window.Drawflow) return Promise.resolve();
  if (drawflowReady) return drawflowReady;
  drawflowReady = new Promise((resolve, reject) => {
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = DRAWFLOW_CSS;
    document.head.appendChild(css);
    const define = window.define; window.define = undefined;  // как с plotly: не регистрироваться в AMD-загрузчике Monaco
    const s = document.createElement("script");
    s.src = DRAWFLOW_JS;
    s.onload = () => { window.define = define; resolve(); };
    s.onerror = () => { window.define = define; reject(new Error("не загрузился Drawflow")); };
    document.head.appendChild(s);
  });
  return drawflowReady;
}

function testsBadge(tests, modes) {
  const parts = arr(modes).map(m => {
    const t = (tests || {})[m];
    return t ? `<span class="${t[0] === t[1] ? "ok" : "err"}" title="${MODE_TITLE[m]}: тесты эталона">${t[0] === t[1] ? "✓" : "✗"} ${t[0]}/${t[1]}</span>`
             : `<span class="muted" title="${MODE_TITLE[m]}: эталон ещё не проверяли">· —</span>`;
  });
  return parts.join(" ");
}

// HTML карточки по виду узла
function cardHtml(d, card) {
  if (d.kind === "slot") {
    return `<div class="bf-slot-body"><div class="bf-kind">слот</div><b>${esc(d.slot)}</b>
      <select class="bf-impl" data-impl-for="${esc(d.key)}">${arr(d.impls).map(i => `<option ${i === d.impl ? "selected" : ""}>${esc(i)}</option>`).join("")}</select></div>`;
  }
  if (d.kind === "draft") {
    return `<div class="bf-body"><div class="bf-kind">черновик · ${esc(LEVEL_NAME[d.level] || "кирпичик")}</div><b class="bf-title">${esc(d.title)}</b>
      <div class="muted small">не сохранено</div></div>`;
  }
  const c = card || {};
  const collapsed = arr(d.children).length ? `<div class="bf-collapsed" title="двойной клик — раскрыть">▸ внутри: ${d.children.length}</div>` : "";
  return `<div class="bf-body" style="--cat:${CAT_COLOR[c.category] || "var(--line)"}"><div class="bf-kind">${esc(LEVEL_NAME[c.level] || "кирпичик")}${c.implements ? ` · слот ${esc(c.implements)}` : ""}</div>
    <b class="bf-title">${esc(c.title || d.title)}</b>
    <div class="bf-meta">${modeHalves(c.statuses)} <span class="small">${testsBadge(c.tests, c.modes)}</span></div>${collapsed}</div>`;
}

function nodeClass(d, card) {
  if (d.kind === "slot") return "bf-node bf-slot";
  if (d.kind === "draft") return `bf-node bf-draft lvl-${d.level || "brick"}`;
  return `bf-node lvl-${(card || {}).level || "brick"}`;
}

// Холст: создать Drawflow в элементе, сетка, зум, мини-карта
function makeCanvas(el, { readonly = false } = {}) {
  el.classList.add("bf-canvas");
  el.innerHTML = `<div class="bf-flow"></div>
    <div class="bf-zoom"><button class="icon-btn" data-z="in" title="приблизить">＋</button><button class="icon-btn" data-z="out" title="отдалить">－</button>
      <button class="icon-btn" data-z="reset" title="масштаб 100%">1:1</button></div>
    <canvas class="bf-minimap" width="180" height="120" title="мини-карта: клик — перейти"></canvas>`;
  const editor = new window.Drawflow($(".bf-flow", el));
  editor.reroute = false;
  editor.zoom_min = 0.3;
  editor.editor_mode = readonly ? "fixed" : "edit";
  editor.start();
  $$("[data-z]", el).forEach(b => b.onclick = () => ({ in: () => editor.zoom_in(), out: () => editor.zoom_out(), reset: () => editor.zoom_reset() })[b.dataset.z]());
  const mini = $(".bf-minimap", el);
  const drawMini = () => {
    const nodes = Object.values(editor.drawflow.drawflow.Home.data);
    const ctx = mini.getContext("2d");
    ctx.clearRect(0, 0, mini.width, mini.height);
    if (!nodes.length) return;
    const xs = nodes.map(n => n.pos_x), ys = nodes.map(n => n.pos_y);
    const minX = Math.min(...xs) - 50, minY = Math.min(...ys) - 50, maxX = Math.max(...xs) + 250, maxY = Math.max(...ys) + 150;
    const k = Math.min(mini.width / (maxX - minX), mini.height / (maxY - minY));
    mini._view = { minX, minY, k };
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--muted") || "#888";
    nodes.forEach(n => ctx.fillRect((n.pos_x - minX) * k, (n.pos_y - minY) * k, 180 * k, 70 * k));
    const box = $(".bf-flow", el).getBoundingClientRect();  // видимая область
    ctx.strokeStyle = "#FFA116";
    ctx.strokeRect((-editor.canvas_x / editor.zoom - minX) * k, (-editor.canvas_y / editor.zoom - minY) * k, box.width / editor.zoom * k, box.height / editor.zoom * k);
  };
  mini.onclick = e => {
    const v = mini._view;
    if (!v) return;
    const r = mini.getBoundingClientRect(), box = $(".bf-flow", el).getBoundingClientRect();
    const x = (e.clientX - r.left) / v.k + v.minX, y = (e.clientY - r.top) / v.k + v.minY;  // точка мира
    editor.canvas_x = -(x * editor.zoom - box.width / 2);
    editor.canvas_y = -(y * editor.zoom - box.height / 2);
    editor.precanvas.style.transform = `translate(${editor.canvas_x}px, ${editor.canvas_y}px) scale(${editor.zoom})`;
    drawMini();
  };
  ["nodeCreated", "nodeRemoved", "nodeMoved", "zoom", "translate", "connectionCreated"].forEach(ev => editor.on(ev, () => requestAnimationFrame(drawMini)));
  return { editor, drawMini };
}

// Раскладка по уровням зависимостей: используемое — левее, использующее — правее
function autoLayout(keys, edges) {
  const depth = {};
  const preds = k => edges.filter(e => e.target === k).map(e => e.source);
  const d = (k, seen = new Set()) => {
    if (depth[k] != null) return depth[k];
    if (seen.has(k)) return 0;
    seen.add(k);
    depth[k] = preds(k).length ? 1 + Math.max(...preds(k).map(p => d(p, seen))) : 0;
    return depth[k];
  };
  keys.forEach(k => d(k));
  const rows = {}, pos = {};
  keys.forEach(k => { const lv = depth[k]; rows[lv] = (rows[lv] || 0) + 1; pos[k] = { x: 60 + lv * 280, y: 40 + (rows[lv] - 1) * 130 }; });
  return pos;
}

// Дерево зависимостей задачи по палитре: {keys, edges} от задачи-корня вниз
function depGraph(rootTask, P) {
  const byName = Object.fromEntries(P.tasks.map(t => [t.name, t]));
  const slotImpl = s => { const sl = P.slots.find(x => x.name === s); return sl ? (sl.default_impl || sl.impls[0]) : null; };
  const keys = new Set(), edges = [], nodes = {};
  const visit = t => {
    const key = `t:${t.id}`;
    if (keys.has(key)) return key;
    keys.add(key);
    nodes[key] = { key, kind: "task", task_id: t.id };
    for (const dep of arr(t.deps)) {
      if (dep.slot) {
        const skey = `s:${dep.slot}`;
        const sl = P.slots.find(x => x.name === dep.slot);
        keys.add(skey);
        nodes[skey] = { key: skey, kind: "slot", slot: dep.slot, impls: sl ? sl.impls : [], impl: slotImpl(dep.slot) };
        edges.push({ source: skey, target: key, name: dep.name });
      } else if (byName[dep.task]) {
        edges.push({ source: visit(byName[dep.task]), target: key, name: dep.name });
      }
    }
    return key;
  };
  visit(rootTask);
  return { keys: [...keys], edges, nodes };
}

// ---------------- экран конструктора ----------------
async function viewBuilder(taskId) {
  view.innerHTML = '<div class="muted spinner">загружаю конструктор</div>';
  await Promise.all([loadDrawflow(), loadMonaco()]);
  const [P, B, T] = await Promise.all([api("/api/builder/palette"), api(`/api/builder/board${taskId ? `?task_id=${taskId}` : ""}`), api("/api/builder/templates")]);
  const cards = Object.fromEntries(P.tasks.map(t => [`t:${t.id}`, t]));
  const root = B.task;
  document.body.classList.add("ide-mode");
  view.innerHTML = `<div class="bf-page">
    <div class="bf-top">
      <a href="${root ? `#/task/${root.id}` : "#/tasks"}" class="muted">←</a>
      <input id="bf-title" placeholder="название задачи (для «Собрать в блок» и новых черновиков)" value="${esc(root ? root.title : "")}" style="min-width:260px">
      <select id="bf-topic"><option value="">— узел в дереве —</option>${topicOptions(P.topics, root ? root.topic_id : null)}</select>
      <input id="bf-tags" placeholder="теги через запятую" value="${esc(root ? root.tags.join(", ") : "")}">
      <span class="grow"></span>
      <span class="muted small" id="bf-status"></span>
      <button id="bf-block" class="ghost" title="выделите карточки (Shift + клик) и соберите их в новую задачу-блок">Собрать в блок</button>
      <button id="bf-check" class="ghost">Проверить всё</button>
      <button id="bf-cancel" class="ghost">Отмена</button>
      <button id="bf-save" class="primary">Сохранить</button>
    </div>
    <div class="bf-cols">
      <div class="bf-palette card" id="bf-palette"></div>
      <div class="bf-center" id="bf-center"><div class="bf-msg" id="bf-msg" hidden></div></div>
      <div class="bf-inspector card" id="bf-inspector"><p class="muted">Выберите карточку — здесь её README, эталоны обоих режимов, тесты, data/ и task.json.</p></div>
    </div></div>`;
  const center = $("#bf-center");
  const canvasEl = document.createElement("div");
  center.prepend(canvasEl);
  const { editor, drawMini } = makeCanvas(canvasEl);
  const byKey = {}, idOf = {};  // ключ карточки <-> id узла Drawflow
  let multi = new Set(), selected = null, dirty = false;
  const status = text => { $("#bf-status").textContent = text; };
  const markDirty = () => { dirty = true; status("есть несохранённые изменения"); };

  function addNode(d, x, y) {
    if (idOf[d.key]) return idOf[d.key];
    const card = cards[d.key];
    if (d.kind === "task" && !card) return null;
    const id = editor.addNode(d.key, d.kind === "slot" ? 0 : 1, 1, x, y, nodeClass(d, card), { key: d.key }, cardHtml(d, card));
    byKey[d.key] = d;
    idOf[d.key] = id;
    bindNode(d);
    return id;
  }
  function refreshNode(key) {
    const d = byKey[key], el = $(`#node-${idOf[key]}`);
    if (!d || !el) return;
    $(".drawflow_content_node", el).innerHTML = cardHtml(d, cards[key]);
    el.className = el.className.replace(/bf-node[^]*?(?= selected|$)/, nodeClass(d, cards[key]));
    bindNode(d);
  }
  function bindNode(d) {
    const el = $(`#node-${idOf[d.key]}`);
    if (!el) return;
    const sel = $(".bf-impl", el);
    if (sel) {
      sel.onmousedown = e => e.stopPropagation();
      sel.onchange = () => { d.impl = sel.value; markDirty(); };
    }
    el.ondblclick = () => { if (arr(d.children).length) expand(d.key); };
  }
  function edgeList() {
    const out = [];
    for (const [key, id] of Object.entries(idOf)) {
      const node = editor.getNodeFromId(id);
      for (const c of node.outputs.output_1?.connections || []) {
        const target = Object.keys(idOf).find(k => idOf[k] === +c.node);
        if (target) out.push({ source: key, target, name: (byKey[target].names || {})[key] || "" });
      }
    }
    return out;
  }
  function connect(src, dst) { if (idOf[src] && idOf[dst]) editor.addConnection(idOf[src], idOf[dst], "output_1", "input_1"); }

  // ---- загрузка доски: сохранённая раскладка или дерево зависимостей корня ----
  function load(board) {
    editor.clear();
    for (const k of Object.keys(idOf)) { delete idOf[k]; delete byKey[k]; }
    multi = new Set();
    if (board && arr(board.nodes).length) {
      board.nodes.forEach(n => addNode(n.data, n.x, n.y));
      arr(board.edges).forEach(e => connect(e.source, e.target));
    } else if (root) {
      const g = depGraph(P.tasks.find(t => t.id === root.id), P);
      const pos = autoLayout(g.keys, g.edges);
      g.keys.forEach(k => addNode(g.nodes[k], pos[k].x, pos[k].y));
      g.edges.forEach(e => connect(e.source, e.target));
    }
    if (!Object.keys(idOf).length) $("#bf-msg").hidden = false, showMsg("Пустой холст: перетащите кирпичики из палитры или шаблон — «Кирпичик-функция (sklearn)», «Слой (torch)», «Метрика», «Пайплайн-стена».", "muted");
    dirty = false;
    status("");
    requestAnimationFrame(drawMini);
  }
  function boardState() {
    const nodes = Object.entries(idOf).map(([key, id]) => { const n = editor.getNodeFromId(id); return { data: byKey[key], x: n.pos_x, y: n.pos_y }; });
    return { nodes, edges: edgeList().map(({ source, target }) => ({ source, target })) };
  }
  function showMsg(text, cls = "err") {
    const m = $("#bf-msg");
    m.className = `bf-msg ${cls}`;
    m.textContent = text;
    m.hidden = false;
    clearTimeout(showMsg.t);
    if (cls === "err") showMsg.t = setTimeout(() => { m.hidden = true; }, 6000);
  }

  // ---- циклы: стрелка, после которой источник зависит от получателя, отклоняется ----
  function depsOf(key) {
    const d = byKey[key];
    const fromBoard = edgeList().filter(e => e.target === key).map(e => e.source);
    if (d?.kind !== "task") return fromBoard;
    const t = cards[key];
    const byName = Object.fromEntries(P.tasks.map(x => [x.name, x]));
    const known = arr(t?.deps).map(dep => dep.task && byName[dep.task] ? `t:${byName[dep.task].id}` : null).filter(Boolean);
    return [...new Set([...fromBoard, ...known])];
  }
  function findPath(from, to, seen = new Set()) {  // путь по «использует»: from -> … -> to
    if (from === to) return [from];
    if (seen.has(from)) return null;
    seen.add(from);
    for (const dep of depsOf(from)) {
      const p = findPath(dep, to, seen);
      if (p) return [from, ...p];
    }
    return null;
  }
  const titleOf = key => byKey[key]?.kind === "slot" ? `слот ${byKey[key].slot}` : (cards[key]?.title || byKey[key]?.title || key);
  editor.on("connectionCreated", ({ output_id, input_id }) => {
    const src = Object.keys(idOf).find(k => idOf[k] === +output_id), dst = Object.keys(idOf).find(k => idOf[k] === +input_id);
    const drop = msg => {
      editor.removeSingleConnection(output_id, input_id, "output_1", "input_1");
      [src, dst].forEach(k => { const el = $(`#node-${idOf[k]}`); el?.classList.add("bf-cycle"); setTimeout(() => el?.classList.remove("bf-cycle"), 2500); });
      showMsg(msg);
    };
    if (byKey[dst]?.kind === "slot") return drop("слот не может ничего использовать: стрелка ведёт от кирпичика к тому, кто его использует");
    const back = findPath(src, dst);  // src уже (транзитивно) использует dst — новая стрелка замкнёт круг
    if (back) return drop(`цикл: ${[...back, src].map(titleOf).join(" → ")} — стрелка отклонена`);
    markDirty();
  });
  editor.on("connectionRemoved", markDirty);
  editor.on("nodeMoved", markDirty);
  editor.on("nodeRemoved", id => {
    const key = Object.keys(idOf).find(k => idOf[k] === +id);
    if (key) { delete idOf[key]; delete byKey[key]; multi.delete(key); }
    markDirty();
  });
  editor.on("nodeSelected", id => {
    const key = Object.keys(idOf).find(k => idOf[k] === +id);
    if (window.event?.shiftKey) {  // Shift + клик — множественный выбор для «Собрать в блок»
      multi.has(key) ? multi.delete(key) : multi.add(key);
      $$(".bf-multi").forEach(e => e.classList.remove("bf-multi"));
      multi.forEach(k => $(`#node-${idOf[k]}`)?.classList.add("bf-multi"));
      status(multi.size ? `выбрано карточек: ${multi.size} — «Собрать в блок»` : "");
      return;
    }
    selected = key;
    inspect(key);
  });

  // ---- палитра ----
  const palette = $("#bf-palette");
  let tab = store.get("bf.tab", "tree");
  function renderPalette() {
    const q = (palette._q || "").toLowerCase();
    const item = t => `<div class="bf-pal-item" draggable="true" data-drag="t:${t.id}" title="${esc(t.name)}">${modeHalves(t.statuses)} <span>${esc(t.title)}</span></div>`;
    let body = "";
    if (tab === "tree") {
      const kids = topicTree(P.topics);
      const walk = (pid, d) => (kids[pid] || []).map(n => {
        const own = P.tasks.filter(t => t.topic_id === n.id);
        return `<details ${d < 1 ? "open" : ""}><summary style="padding-left:${d * 10}px">${esc(n.name)} <span class="muted small">${own.length || ""}</span></summary>
          <div style="padding-left:${d * 10 + 8}px">${own.map(item).join("")}${walk(n.id, d + 1)}</div></details>`;
      }).join("");
      body = walk("root", 0);
    } else if (tab === "search") {
      const tasks = P.tasks.filter(t => (t.title + " " + t.name + " " + t.tags.join(" ")).toLowerCase().includes(q));
      const slots = P.slots.filter(s => (s.name + " " + s.title).toLowerCase().includes(q));
      body = `<input id="bf-q" placeholder="поиск задач и слотов" value="${esc(palette._q || "")}" style="width:100%;margin-bottom:6px">
        ${slots.map(s => `<div class="bf-pal-item bf-pal-slot" draggable="true" data-drag="s:${esc(s.name)}"><span class="badge">слот</span> ${esc(s.name)} <span class="muted small">${esc(s.signature || "")}</span></div>`).join("")}
        ${tasks.map(item).join("") || '<p class="muted small">ничего не найдено</p>'}`;
    } else {
      const byName = Object.fromEntries(P.tasks.map(t => [t.name, t]));
      body = P.map_rows.map(r => `<details><summary>${esc(r.title)}</summary>${r.bricks.map(b => byName[b] ? item(byName[b])
        : `<div class="bf-pal-item bf-planned" draggable="true" data-drag="planned:${esc(b)}" title="задачи ещё нет — перетащите, будет черновик">◌ ${esc(b)}</div>`).join("")}</details>`).join("");
    }
    palette.innerHTML = `<div class="seg" style="margin:0 0 8px">${[["tree", "Дерево"], ["search", "Поиск"], ["map", "Карта"]].map(([k, n]) => `<button data-ptab="${k}" class="${k === tab ? "sel" : ""}">${n}</button>`).join("")}</div>
      <div class="label">Шаблоны</div>${Object.entries(T).map(([k, t]) => `<div class="bf-pal-item bf-pal-tpl" draggable="true" data-drag="tpl:${k}">＋ ${esc({ sklearn_function: "Кирпичик-функция (sklearn)", torch_layer: "Слой (torch)", metric: "Метрика", wall: "Пайплайн-стена" }[k] || t.title)}</div>`).join("")}
      <div class="label mt">${{ tree: "Дерево тем", search: "Задачи и слоты", map: "Карта навыков" }[tab]}</div>${body}`;
    $$("[data-ptab]", palette).forEach(b => b.onclick = () => { tab = b.dataset.ptab; store.set("bf.tab", tab); renderPalette(); });
    const qi = $("#bf-q", palette);
    if (qi) { qi.oninput = () => { palette._q = qi.value; renderPalette(); const n = $("#bf-q", palette); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }; }
    $$("[data-drag]", palette).forEach(el => el.ondragstart = e => e.dataTransfer.setData("text/bf", el.dataset.drag));
  }
  renderPalette();

  // ---- перетаскивание из палитры на холст ----
  let draftN = 0;
  canvasEl.ondragover = e => e.preventDefault();
  canvasEl.ondrop = e => {
    e.preventDefault();
    const what = e.dataTransfer.getData("text/bf");
    if (!what) return;
    const pre = editor.precanvas, k = pre.clientWidth / (pre.clientWidth * editor.zoom);
    const x = e.clientX * k - pre.getBoundingClientRect().x * k, y = e.clientY * k - pre.getBoundingClientRect().y * k;
    $("#bf-msg").hidden = true;
    if (what.startsWith("t:")) {
      if (idOf[what]) return showMsg("эта карточка уже на холсте", "muted");
      addNode({ key: what, kind: "task", task_id: +what.slice(2) }, x, y);
      const g = depGraph(cards[what], P);  // её зависимости — тоже на холст, со стрелками (иначе при сохранении они бы потерялись)
      const pos = autoLayout(g.keys, g.edges);
      g.keys.forEach(kk => addNode(g.nodes[kk], x + pos[kk].x - pos[what].x, y + pos[kk].y - pos[what].y));
      g.edges.forEach(ed => { if (!edgeList().some(x2 => x2.source === ed.source && x2.target === ed.target)) connect(ed.source, ed.target); });
    } else if (what.startsWith("s:")) {
      const sl = P.slots.find(s => s.name === what.slice(2));
      addNode({ key: what, kind: "slot", slot: sl.name, impls: sl.impls, impl: sl.default_impl || sl.impls[0] }, x, y);
    } else {
      const tplKey = what.startsWith("tpl:") ? what.slice(4) : "sklearn_function";
      const tpl = T[tplKey];
      const title = what.startsWith("planned:") ? what.slice(8) : `${tpl.title} ${++draftN}`;
      const key = `d:${Date.now().toString(36)}${draftN}`;
      addNode({ key, kind: "draft", level: tpl.level, title, files: { ...tpl.files }, meta: { ...tpl.meta }, implements: tpl.implements, main: tpl.main,
                topic_id: $("#bf-topic").value ? +$("#bf-topic").value : null, tags: [] }, x, y);
      selected = key;
      inspect(key);
    }
    markDirty();
  };

  // ---- «Собрать в блок» и раскрытие ----
  $("#bf-block").onclick = async () => {
    const members = [...multi].filter(k => byKey[k]);
    if (!members.length) return showMsg("выделите карточки: Shift + клик по каждой", "muted");
    const drafts = members.filter(k => byKey[k].kind === "draft");
    if (drafts.length) return showMsg("черновики сначала сохраните («Сохранить»), потом собирайте в блок");
    const title = $("#bf-title").value.trim() || prompt("Название новой задачи-блока", "новый блок");
    if (!title) return;
    try {
      const card = await api("/api/builder/block", { method: "POST", json: { title, members, topic_id: $("#bf-topic").value ? +$("#bf-topic").value : null,
        tags: $("#bf-tags").value.split(",").map(s => s.trim()).filter(Boolean) } });
      P.tasks.push(card);
      cards[`t:${card.id}`] = card;
      const pos = members.map(k => editor.getNodeFromId(idOf[k]));
      const cx = Math.max(...pos.map(p => p.pos_x)) + 260, cy = pos.reduce((s, p) => s + p.pos_y, 0) / pos.length;
      const children = members.map(k => ({ data: byKey[k], x: editor.getNodeFromId(idOf[k]).pos_x, y: editor.getNodeFromId(idOf[k]).pos_y }));
      const outer = edgeList().filter(e => members.includes(e.source) && !members.includes(e.target));  // кто использовал выбранные
      members.forEach(k => editor.removeNodeId(`node-${idOf[k]}`));
      const key = `t:${card.id}`;
      addNode({ key, kind: "task", task_id: card.id, children }, cx, cy);
      outer.forEach(e => connect(key, e.target));
      multi = new Set();
      markDirty();
      status(`создана задача-блок «${card.title}» · зависимостей: ${card.deps.length} — «Сохранить», чтобы запомнить раскладку`);
      toast(`блок «${card.title}» создан — зависимости: ${card.deps.map(d => d.name).join(", ")}`);
    } catch (e) { showMsg(e.message); }
  };
  function expand(key) {  // двойной клик по свёрнутому блоку: вернуть карточки и стрелки в блок
    const d = byKey[key];
    const base = editor.getNodeFromId(idOf[key]);
    d.children.forEach(c => addNode(c.data, c.x, c.y));
    d.children.forEach(c => connect(c.data.key, key));
    d.children = [];
    refreshNode(key);
    void base;
    markDirty();
  }

  // ---- инспектор ----
  async function inspect(key) {
    const box = $("#bf-inspector"), d = byKey[key];
    if (!d) { box.innerHTML = ""; return; }
    if (box._ed) { box._ed.dispose(); box._ed = null; }
    if (d.kind === "slot") {
      const sl = P.slots.find(s => s.name === d.slot) || {};
      box.innerHTML = `<h3>Слот ${esc(d.slot)}</h3><p class="mono small">${esc(sl.signature || "")}</p>
        <p class="small">Реализации: ${arr(sl.impls).map(i => `<span class="badge">${esc(i)}</span>`).join(" ")}</p>
        <p class="muted small">Выбор реализации — в карточке; при старте составной задачи он предлагается на экране сборки.</p>`;
      return;
    }
    const isTask = d.kind === "task";
    const card = cards[key];
    const tabs = [["readme", "README"], ["library", "Эталон · библиотека"], ["scratch", "Эталон · с нуля"], ["tests", "Тесты"], ["data", "data/"], ["meta", "task.json"]];
    let cur = box._tab || "readme";
    const used = edgeList().filter(e => e.source === key).map(e => e.target);
    box.innerHTML = `<div class="row"><b class="grow">${esc(isTask ? card.title : d.title)}</b>${isTask ? `<a class="small" href="#/task/${card.id}">открыть</a>` : '<span class="badge">черновик</span>'}</div>
      ${isTask ? `<div class="mt">${modeHalves(card.statuses)} <span class="small">${testsBadge(card.tests, card.modes)}</span></div>` :
        `<input id="bf-dtitle" value="${esc(d.title)}" style="width:100%;margin-top:6px">`}
      <div class="seg mt" style="flex-wrap:wrap">${tabs.map(([k, n]) => `<button data-itab="${k}" class="${k === cur ? "sel" : ""}">${n}</button>`).join("")}</div>
      <div id="bf-ibody" class="mt"></div>
      <div class="row mt">${(isTask ? card.modes : MODES).map(m => `<button class="small" data-icheck="${m}" ${isTask ? "" : 'disabled title="сначала сохраните черновик"'}>Проверить эталон · ${MODE_NAME[m]}</button>`).join("")}</div>
      <div id="bf-icheck" class="mt"></div>
      <div class="label mt">Где используется</div><div class="small" id="bf-iused">${used.map(k => `<div>→ ${esc(titleOf(k))}</div>`).join("") || '<span class="muted">на холсте стрелок отсюда нет</span>'}</div>`;
    if (isTask) api(`/api/tasks/${card.id}/graph`).then(g => {
      const ups = arr(g.up).filter(u => u.depth === 0).map(u => `<div>↗ <a href="#/task/${u.task_id}">${esc(u.title)}</a></div>`).join("");
      if (ups) $("#bf-iused").insertAdjacentHTML("beforeend", `<div class="muted small mt">в сохранённых задачах:</div>${ups}`);
    }).catch(() => {});
    const dt = $("#bf-dtitle", box);
    if (dt) dt.oninput = () => { d.title = dt.value; refreshNode(key); markDirty(); };
    $$("[data-itab]", box).forEach(b => b.onclick = () => { box._tab = b.dataset.itab; inspect(key); });
    $$("[data-icheck]", box).forEach(b => b.onclick = async () => {
      const out = $("#bf-icheck", box);
      out.innerHTML = '<div class="muted spinner small">проверяю эталон</div>';
      const { job } = await api(`/api/tasks/${card.id}/check?mode=${b.dataset.icheck}`, { method: "POST" });
      const r = (await followJob(job, () => {})).result;
      out.innerHTML = testsHtml(r.check);
      const m = r.check.modes?.[b.dataset.icheck];
      if (m) { card.tests = { ...card.tests, [b.dataset.icheck]: [m.passed, m.total] }; refreshNode(key); }
    });
    const ib = $("#bf-ibody", box);
    // файлы вкладки: у задачи — с диска (файловое API папки задачи), у черновика — из карточки
    const pathsFor = async () => {
      const prefix = { readme: ["description.md"], library: ["reference/library/"], scratch: ["reference/scratch/", "reference/"], tests: ["tests/"], data: ["data/"] }[cur];
      if (!isTask) return Object.keys(d.files || {}).filter(p => prefix.some(x => x.endsWith("/") ? p.startsWith(x) : p === x))
        .concat(cur === "readme" && !d.files["description.md"] ? ["description.md"] : []);
      const list = async dir => { try { return await api(`/api/tasks/${card.id}/files?path=${encodeURIComponent(dir)}`); } catch { return []; } };
      if (cur === "readme") return ["description.md"];
      const out = [];
      const walk = async dir => { for (const f of await list(dir)) { if (f.dir) await walk(f.path); else out.push(f.path); } };
      if (cur === "scratch") { await walk("reference/scratch"); if (!out.length) (await list("reference")).filter(f => !f.dir).forEach(f => out.push(f.path)); }
      else await walk({ library: "reference/library", tests: "tests", data: "data" }[cur]);
      return out;
    };
    if (cur === "meta") {
      let meta = {};
      if (isTask) { try { meta = JSON.parse((await api(`/api/tasks/${card.id}/file?path=task.json`)).content); } catch { meta = {}; } } else meta = d.meta || {};
      const fields = [["library_function", "функция библиотеки"], ["required_names", "required_names — что должно быть вызвано (через запятую)"],
                      ["forbidden_names", "forbidden_names — что нельзя «С нуля»"], ["forbidden_modules", "forbidden_modules"], ["signature", "сигнатура"]];
      ib.innerHTML = fields.map(([k, n]) => `<label class="small muted">${n}</label><input data-mf="${k}" value="${esc(Array.isArray(meta[k]) ? meta[k].join(", ") : meta[k] || "")}" style="width:100%;margin-bottom:6px">`).join("")
        + `<label class="small muted">required_kwargs — JSON {"функция": ["параметр"]}</label><textarea data-mf="required_kwargs" class="mono" rows="3" style="width:100%">${esc(JSON.stringify(meta.required_kwargs || {}))}</textarea>
           <button class="small mt" id="bf-msave">${isTask ? "Записать task.json" : "Применить"}</button>`;
      $("#bf-msave", ib).onclick = async () => {
        for (const el of $$("[data-mf]", ib)) {
          const k = el.dataset.mf, v = el.value.trim();
          if (k === "required_kwargs") { try { meta[k] = v ? JSON.parse(v) : {}; } catch { return toast("required_kwargs — не JSON", true); } }
          else if (["required_names", "forbidden_names", "forbidden_modules"].includes(k)) meta[k] = v.split(",").map(s => s.trim()).filter(Boolean);
          else meta[k] = v;
        }
        if (isTask) { await api(`/api/tasks/${card.id}/file`, { method: "PUT", json: { path: "task.json", content: JSON.stringify(meta, null, 2) + "\n" } }); toast("task.json записан — «Сохранить версию» на странице редактора"); }
        else { d.meta = meta; toast("поля черновика обновлены"); markDirty(); }
      };
      return;
    }
    const paths = await pathsFor();
    if (cur === "data") { ib.innerHTML = paths.length ? paths.map(p => `<div class="mono small">${esc(p)}</div>`).join("") : '<p class="muted small">data/ пуста</p>'; return; }
    ib.innerHTML = `<select id="bf-file" style="width:100%">${(paths.length ? paths : [{ library: "reference/library/solution.py", scratch: "reference/scratch/solution.py", tests: "tests/test_solution.py", readme: "description.md" }[cur]])
      .map(p => `<option>${esc(p)}</option>`).join("")}</select><div class="bf-code" id="bf-code"></div>
      <div class="row mt"><button class="small" id="bf-fsave">${isTask ? "Записать файл" : "Применить"}</button>${isTask ? `<button class="small ghost" id="bf-fver">Сохранить версию</button>` : ""}</div>`;
    const open = async path => {
      let text = "";
      if (isTask) { try { text = (await api(`/api/tasks/${card.id}/file?path=${encodeURIComponent(path)}`)).content; } catch { text = ""; } }
      else text = (d.files || {})[path] || "";
      if (box._ed) box._ed.dispose();
      box._ed = monaco.editor.create($("#bf-code", ib), { value: text, language: path.endsWith(".py") ? "python" : "markdown", automaticLayout: true,
        minimap: { enabled: false }, fontSize: 12, fontFamily: "JetBrains Mono, Menlo, monospace", scrollBeyondLastLine: false, wordWrap: "on" });
      box._path = path;
    };
    $("#bf-file", ib).onchange = e => open(e.target.value);
    await open($("#bf-file", ib).value);
    $("#bf-fsave", ib).onclick = async () => {
      const text = box._ed.getValue();
      if (isTask) { await api(`/api/tasks/${card.id}/file`, { method: "PUT", json: { path: box._path, content: text } }); toast(`${box._path} записан`); }
      else { d.files = { ...d.files, [box._path]: text }; toast("файл черновика обновлён"); markDirty(); }
    };
    const fv = $("#bf-fver", ib);
    if (fv) fv.onclick = async () => {
      try { const r = await api(`/api/tasks/${card.id}/version`, { method: "POST" }); toast(r.status === "unchanged" ? "изменений нет" : `версия ${r.version}`); }
      catch (e) { toast(e.message, true); }
    };
  }

  // ---- верхние кнопки ----
  $("#bf-save").onclick = async () => {
    const drafts = Object.values(byKey).filter(d => d.kind === "draft").map(d => ({ key: d.key.slice(2), title: d.title, topic_id: d.topic_id ?? ($("#bf-topic").value ? +$("#bf-topic").value : null),
      tags: d.tags || [], files: d.files || {}, meta: d.meta || {}, main: d.main || "solution.py", implements: d.implements || "" }));
    try {
      const r = await api("/api/builder/save", { method: "POST", json: { task_id: root ? root.id : null, drafts, edges: edgeList(), board: boardState() } });
      const fresh = await api("/api/builder/palette");  // черновики стали задачами: обновить карточки
      P.tasks = fresh.tasks;
      fresh.tasks.forEach(t => { cards[`t:${t.id}`] = t; });
      for (const [dk, tid] of Object.entries(r.created)) {  // черновик -> карточка задачи на том же месте
        const old = `d:${dk}`, n = editor.getNodeFromId(idOf[old]);
        const ins = edgeList().filter(e => e.target === old).map(e => e.source), outs = edgeList().filter(e => e.source === old).map(e => e.target);
        editor.removeNodeId(`node-${idOf[old]}`);
        addNode({ key: `t:${tid}`, kind: "task", task_id: tid }, n.pos_x, n.pos_y);
        ins.forEach(s => connect(s, `t:${tid}`));
        outs.forEach(t2 => connect(`t:${tid}`, t2));
      }
      Object.keys(idOf).forEach(refreshNode);
      await api("/api/builder/board", { method: "PUT", json: { task_id: root ? root.id : null, board: boardState() } });
      dirty = false;
      status(`сохранено: новых задач ${Object.keys(r.created).length}, обновлены зависимости у ${r.changed.length}`);
      renderPalette();
    } catch (e) { showMsg(e.message); }
  };
  $("#bf-cancel").onclick = async () => {
    if (dirty && !confirm("Отменить несохранённые изменения на холсте?")) return;
    const b = await api(`/api/builder/board${root ? `?task_id=${root.id}` : ""}`);
    load(b.board);
  };
  $("#bf-check").onclick = async () => {
    const tasks = Object.keys(idOf).filter(k => byKey[k].kind === "task");
    for (const [i, k] of tasks.entries()) {
      const c = cards[k];
      for (const m of c.modes) {
        status(`проверяю ${i + 1}/${tasks.length}: ${c.title} · ${MODE_NAME[m]}`);
        const { job } = await api(`/api/tasks/${c.id}/check?mode=${m}`, { method: "POST" });
        const r = (await followJob(job, () => {})).result;
        const s = r.check.modes?.[m];
        if (s) c.tests = { ...c.tests, [m]: [s.passed, s.total] };
        refreshNode(k);
      }
    }
    const bad = tasks.filter(k => Object.values(cards[k].tests || {}).some(([p, t]) => p !== t));
    status(bad.length ? `проверено: с ошибками — ${bad.map(titleOf).join(", ")}` : `проверено: все эталоны зелёные (${tasks.length} задач)`);
  };
  load(B.board);
  current = { leaveGuard: () => !dirty || confirm("На холсте есть несохранённые изменения. Уйти?"), dispose: () => { document.body.classList.remove("ide-mode"); } };
}

// ---------------- тот же холст — только просмотр ----------------
// mode "compose": вкладка «Состав» (вниз — из чего, вверх — где используется);
// mode "assemble": экран сборки — у каждой карточки выбор источника.
async function renderBoardView(el, taskId, opts = {}) {
  await loadDrawflow();
  const P = await api("/api/builder/palette");
  const cards = Object.fromEntries(P.tasks.map(t => [`t:${t.id}`, t]));
  const rootCard = P.tasks.find(t => t.id === +taskId);
  el.style.height = opts.height || "520px";
  const { editor, drawMini } = makeCanvas(el, { readonly: true });
  const g = depGraph(rootCard, P);
  let keys = g.keys, edges = g.edges;
  if (opts.assemble) {  // экран сборки: только узлы сборки (режим задачи учтён на сервере)
    const nodes = arr(opts.assemble.nodes);
    const byName = Object.fromEntries(P.tasks.map(t => [t.name, t]));
    keys = [`t:${rootCard.id}`];
    edges = [];
    nodes.forEach(n => {
      const key = n.kind === "slot" ? `s:${n.slot}` : `t:${n.task_id}`;
      if (!keys.includes(key)) keys.push(key);
      g.nodes[key] = n.kind === "slot" ? { key, kind: "slot", slot: n.slot, impls: arr(n.impls).map(i => i.name), impl: n.task_name, asmName: n.name }
                                      : { key, kind: "task", task_id: n.task_id, asmName: n.name };
      const parent = n.parent ? nodes.find(x => x.name === n.parent) : null;
      edges.push({ source: key, target: parent ? (parent.kind === "slot" ? `s:${parent.slot}` : `t:${parent.task_id}`) : `t:${rootCard.id}` });
      if (n.kind === "slot" && byName[n.task_name]) cards[`s:${n.slot}`] = byName[n.task_name];
    });
  }
  const ups = opts.assemble ? [] : arr((await api(`/api/tasks/${taskId}/graph`)).up);
  const pos = autoLayout(keys, edges);
  const ids = {};
  keys.forEach(k => {
    const d = g.nodes[k];
    const extra = opts.assemble && d.asmName ? opts.sourceHtml(d.asmName, opts.assemble.nodes.find(n => n.name === d.asmName)) : "";
    ids[k] = editor.addNode(k, d.kind === "slot" ? 0 : 1, 1, pos[k].x, pos[k].y, nodeClass(d, cards[k]) + (k === `t:${rootCard.id}` ? " bf-root" : ""), {},
                            cardHtml(d, cards[k]) + extra);
    const node = $(`#node-${ids[k]}`, el);
    if (d.kind === "task" && !opts.assemble) node.ondblclick = () => { location.hash = `#/task/${d.task_id}`; };
    node.title = opts.assemble ? "" : "двойной клик — перейти к задаче";
  });
  edges.forEach(e => editor.addConnection(ids[e.source], ids[e.target], "output_1", "input_1"));
  const maxX = Math.max(...keys.map(k => pos[k].x));
  const upIds = { [rootCard.id]: ids[`t:${rootCard.id}`] };
  ups.forEach((u, i) => {  // где используется — правее корня
    const id = editor.addNode(`u${u.task_id}`, 1, 1, maxX + 300 + u.depth * 280, 40 + i * 120, "bf-node lvl-block", {}, cardHtml({ kind: "task" }, cards[`t:${u.task_id}`]));
    upIds[u.task_id] = id;
    $(`#node-${id}`, el).ondblclick = () => { location.hash = `#/task/${u.task_id}`; };
    $(`#node-${id}`, el).title = "двойной клик — перейти к задаче";
  });
  ups.forEach(u => { if (upIds[u.child]) editor.addConnection(upIds[u.child], upIds[u.task_id], "output_1", "input_1"); });
  $$(".bf-impl", el).forEach(s => { s.disabled = true; s.title = "реализация слота выбирается в таблице ниже / в конструкторе"; });
  if (opts.assemble) $$(".bf-src", el).forEach(s => { s.onmousedown = e => e.stopPropagation(); s.onclick = e => e.stopPropagation(); });
  requestAnimationFrame(drawMini);
  return editor;
}
