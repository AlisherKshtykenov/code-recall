// Конструктор задач — визуальная доска на Drawflow: палитра слева, холст в центре, инспектор справа.
// Стрелка от кирпичика к тому, кто его использует, = зависимость. Тот же холст — «только просмотр»
// во вкладке «Состав» и на экране сборки. Карточки и состояния — design/CODE_RECALL.pdf, стр. 5–15, 27.

const DRAWFLOW_JS = "https://cdn.jsdelivr.net/npm/drawflow@0.0.60/dist/drawflow.min.js";
const DRAWFLOW_CSS = "https://cdn.jsdelivr.net/npm/drawflow@0.0.60/dist/drawflow.min.css";
const LEVEL_NAME = { brick: "кирпичик", block: "блок", wall: "стена" };
const TPL_INFO = {  // шаблоны на пустом холсте (стр. 6)
  sklearn_function: ["Кирпичик-функция", "def f(...) -> ...", "Эталон в двух режимах и тесты. Подходит для метрик, loss, утилит.", "c-pre"],
  torch_layer: ["Слой (torch)", "class Layer(nn.Module)", "__init__ + forward, тесты проверяют формы и градиенты.", "c-lay"],
  metric: ["Метрика", "metric(y_true, y_pred) -> float", "Сразу реализует слот metric, пример со sklearn.metrics.", "c-met"],
  wall: ["Пайплайн-стена", "данные → модель → обучение → оценка", "Рамка со слотами loss, optimizer, metric.", "c-mod"],
};
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

// наконечники стрелок: обычная связь и связь-цикл (один раз на страницу)
function ensureArrowDefs() {
  if ($("#bf-defs")) return;
  document.body.insertAdjacentHTML("beforeend", `<svg id="bf-defs" width="0" height="0" style="position:absolute"><defs>
    <marker id="bf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 1 9 5 0 9z" style="fill: var(--text-3)"/></marker>
    <marker id="bf-arrow-cyc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 1 9 5 0 9z" style="fill: var(--fail)"/></marker>
  </defs></svg>`);
}

// значок тестов эталона: «✓ 12/12», «✗ 3/5» (хуже из режимов), «нет тестов»
function testsMark(c) {
  const t = Object.entries((c || {}).tests || {});
  if (!t.length) return "";
  const bad = t.find(([, [p, n]]) => p !== n);
  const [m, [p, n]] = bad || t.reduce((a, b) => (b[1][1] > a[1][1] ? b : a));
  return `<span class="cn-tests ${bad ? "fail" : "ok"}" title="тесты эталона · ${MODE_NAME[m]}">${bad ? "✗" : "✓"} ${p}/${n}</span>`;
}

// HTML карточки по виду узла (стр. 15): полоска категории, имя, тесты, категория, режимы
function cardHtml(d, card, extra = "") {
  const c = card || {};
  const cat = c.category || d.category || "";
  const foot = `<div class="cn-foot">${catTag(cat)}<span class="grow"></span>${extra || (c.statuses ? modeHalves(c.statuses) : "")}</div>`;
  if (d.kind === "slot") {
    return `<div class="cn ${catClass(cat)}"><div class="cn-top"><span class="cn-kind">слот · ${esc(d.slot)}</span>${testsMark(c)}</div>
      <select class="bf-impl" data-impl-for="${esc(d.key)}">${arr(d.impls).map(i => `<option ${i === d.impl ? "selected" : ""}>${esc(i)}</option>`).join("")}</select>${foot}</div>`;
  }
  if (d.kind === "draft") {
    return `<div class="cn ${catClass(cat)}"><div class="cn-top"><b class="cn-title">${esc(d.title)}</b><span class="cn-tests none">нет тестов</span></div>
      <div class="cn-sub">черновик · ${esc(LEVEL_NAME[d.level] || "кирпичик")}</div>${foot}</div>`;
  }
  const kids = arr(d.children).length;
  const sub = d.wallOut ? "выход стены" : kids ? `${kids} ${plural(kids, "кирпичик", "кирпичика", "кирпичиков")} · двойной клик`
    : c.level === "block" ? arr(c.deps).map(x => x.name).slice(0, 4).join(" · ") : "";
  return `<div class="cn ${catClass(cat)}" title="${esc(c.title || "")}"><div class="cn-top"><b class="cn-title">${esc(d.wallOut ? d.wallOut : c.name || d.title)}</b>${testsMark(c)}</div>
    ${sub ? `<div class="cn-sub">${esc(sub)}</div>` : ""}${foot}</div>`;
}

function nodeClass(d, card) {
  const fail = Object.values((card || {}).tests || {}).some(([p, n]) => p !== n) ? " bf-fail" : "";
  if (d.kind === "slot") return "bf-node bf-slot" + fail;
  if (d.kind === "draft") return `bf-node bf-draft lvl-${d.level || "brick"}`;
  return `bf-node lvl-${d.wallOut ? "block" : (card || {}).level === "wall" ? "block" : (card || {}).level || "brick"}${fail}`;
}

// Холст: Drawflow в элементе, точки 1 px через 20 px, зум «− 76% + ⛶», мини-карта
function makeCanvas(el, { readonly = false } = {}) {
  ensureArrowDefs();
  el.classList.add("bf-canvas");
  el.innerHTML = `<div class="bf-flow"></div>
    <div class="bf-zoom"><button class="icon-btn" data-z="out" title="отдалить">−</button><span class="bf-zv">100%</span>
      <button class="icon-btn" data-z="in" title="приблизить">+</button><button class="icon-btn" data-z="fit" title="показать всё">⛶</button></div>
    <canvas class="bf-minimap" width="200" height="130" title="мини-карта: клик — перейти"></canvas>`;
  const editor = new window.Drawflow($(".bf-flow", el));
  editor.reroute = false;
  editor.zoom_min = 0.3;
  editor.curvature = 0.5;
  editor.editor_mode = readonly ? "fixed" : "edit";
  editor.start();
  const flow = $(".bf-flow", el);
  const apply = () => { editor.precanvas.style.transform = `translate(${editor.canvas_x}px, ${editor.canvas_y}px) scale(${editor.zoom})`; paint(); };
  const fit = () => {
    const nodes = Object.values(editor.drawflow.drawflow.Home.data);
    if (!nodes.length) return;
    const box = flow.getBoundingClientRect();
    const xs = nodes.map(n => n.pos_x), ys = nodes.map(n => n.pos_y);
    const minX = Math.min(...xs) - 40, minY = Math.min(...ys) - 60, maxX = Math.max(...xs) + 260, maxY = Math.max(...ys) + 140;
    editor.zoom = Math.max(editor.zoom_min, Math.min(1, box.width / (maxX - minX), box.height / (maxY - minY)));
    // Drawflow масштабирует от центра элемента: сдвиг считаем с поправкой на это
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    editor.canvas_x = (box.width / 2 - cx) * editor.zoom;
    editor.canvas_y = (box.height / 2 - cy) * editor.zoom;
    editor.zoom_last_value = editor.zoom;
    apply();
  };
  $$("[data-z]", el).forEach(b => b.onclick = () => ({ in: () => editor.zoom_in(), out: () => editor.zoom_out(), fit })[b.dataset.z]());
  const mini = $(".bf-minimap", el);
  const paint = () => {
    $(".bf-zv", el).textContent = `${Math.round(editor.zoom * 100)}%`;
    const nodes = Object.values(editor.drawflow.drawflow.Home.data);
    const ctx = mini.getContext("2d");
    ctx.clearRect(0, 0, mini.width, mini.height);
    mini.hidden = !nodes.length;
    if (!nodes.length) return;
    const xs = nodes.map(n => n.pos_x), ys = nodes.map(n => n.pos_y);
    const minX = Math.min(...xs) - 60, minY = Math.min(...ys) - 60, maxX = Math.max(...xs) + 260, maxY = Math.max(...ys) + 160;
    const k = Math.min(mini.width / (maxX - minX), mini.height / (maxY - minY));
    mini._view = { minX, minY, k };
    for (const n of nodes) {
      const node = $(`#node-${n.id}`, el), c = node && getComputedStyle($(".cn", node) || node).getPropertyValue("--c").trim();
      ctx.fillStyle = c || tok("--line-2");
      ctx.globalAlpha = .75;
      ctx.fillRect((n.pos_x - minX) * k, (n.pos_y - minY) * k, (node?.offsetWidth || 170) * k, (node?.offsetHeight || 64) * k);
    }
    ctx.globalAlpha = 1;
    const box = flow.getBoundingClientRect();
    ctx.strokeStyle = tok("--accent");
    ctx.lineWidth = 1.5;
    // видимая область: точка экрана (sx, sy) -> мир ((sx - cx) / z + w/2 * (1 - 1/z) …); у Drawflow масштаб от центра
    const z = editor.zoom, wx = x => (x - editor.canvas_x - box.width / 2 * (1 - z)) / z, wy = y => (y - editor.canvas_y - box.height / 2 * (1 - z)) / z;
    ctx.strokeRect((wx(0) - minX) * k, (wy(0) - minY) * k, box.width / z * k, box.height / z * k);
  };
  mini.onclick = e => {
    const v = mini._view;
    if (!v) return;
    const r = mini.getBoundingClientRect(), box = flow.getBoundingClientRect(), z = editor.zoom;
    const x = (e.clientX - r.left) / v.k + v.minX, y = (e.clientY - r.top) / v.k + v.minY;
    editor.canvas_x = box.width / 2 - x * z - box.width / 2 * (1 - z);
    editor.canvas_y = box.height / 2 - y * z - box.height / 2 * (1 - z);
    apply();
  };
  ["nodeCreated", "nodeRemoved", "nodeMoved", "zoom", "translate", "connectionCreated"].forEach(ev => editor.on(ev, () => requestAnimationFrame(paint)));
  return { editor, drawMini: paint, fit };
}

// рамка стены вокруг всех карточек (радиус 14, заголовок 36) — внутри precanvas, масштабируется вместе с холстом
function drawFrame(editor, el, info) {
  let fr = $(".bf-frame", editor.precanvas);
  if (!info) { fr?.remove(); return; }
  const nodes = Object.values(editor.drawflow.drawflow.Home.data);
  if (!nodes.length) { fr?.remove(); return; }
  if (!fr) { fr = document.createElement("div"); fr.className = "bf-frame"; editor.precanvas.prepend(fr); }
  const sz = n => { const d = $(`#node-${n.id}`, el); return [d?.offsetWidth || 170, d?.offsetHeight || 64]; };
  const minX = Math.min(...nodes.map(n => n.pos_x)) - 32, minY = Math.min(...nodes.map(n => n.pos_y)) - 36 - 28;
  const maxX = Math.max(...nodes.map(n => n.pos_x + sz(n)[0])) + 32, maxY = Math.max(...nodes.map(n => n.pos_y + sz(n)[1])) + 32;
  Object.assign(fr.style, { left: `${minX}px`, top: `${minY}px`, width: `${maxX - minX}px`, height: `${maxY - minY}px` });
  fr.innerHTML = `<div class="bf-frame-h">${ICON.wall}<b>${esc(info.title)}</b><span class="faint">стена · ${nodes.length} ${plural(nodes.length, "узел", "узла", "узлов")}</span>
    <span class="grow"></span><span class="faint">${esc(info.hint || "двойной клик по блоку — раскрыть")}</span></div>`;
}

// Раскладка по уровням зависимостей: используемое — левее, использующее — правее.
// В столбце не больше 7 карточек (дальше — соседний подстолбец); порядок — по тем, кто использует (меньше пересечений).
function autoLayout(keys, edges) {
  const depth = {};
  const preds = k => edges.filter(e => e.target === k).map(e => e.source);
  const succ = k => edges.filter(e => e.source === k).map(e => e.target);
  const d = (k, seen = new Set()) => {
    if (depth[k] != null) return depth[k];
    if (seen.has(k)) return 0;
    seen.add(k);
    depth[k] = preds(k).length ? 1 + Math.max(...preds(k).map(p => d(p, seen))) : 0;
    return depth[k];
  };
  keys.forEach(k => d(k));
  const levels = {};
  keys.forEach(k => (levels[depth[k]] ||= []).push(k));
  const order = {}, lv = Object.keys(levels).map(Number).sort((a, b) => b - a);
  for (const l of lv) {  // справа налево: место — среднее мест потребителей
    levels[l].forEach((k, i) => { const s = succ(k).filter(x => order[x] != null); order[k] = s.length ? s.reduce((a, x) => a + order[x], 0) / s.length + i * 1e-3 : i; });
    levels[l].sort((a, b) => order[a] - order[b]).forEach((k, i) => { order[k] = i; });
  }
  const ROWS = 7, CW = 240, RH = 112, pos = {};
  let x = 60;
  for (const l of lv.slice().reverse()) {
    const list = levels[l], cols = Math.ceil(list.length / ROWS), rows = Math.min(ROWS, list.length);
    list.forEach((k, i) => {
      const c = Math.floor(i / ROWS), r = i % ROWS, inCol = Math.min(ROWS, list.length - c * ROWS);
      pos[k] = { x: x + c * CW, y: 60 + (r + (rows - inCol) / 2) * RH };
    });
    x += cols * CW + 30;
  }
  return pos;
}

// Дерево зависимостей задачи по палитре: {keys, edges} от задачи-корня вниз
function depGraph(rootTask, P) {
  const byName = Object.fromEntries(P.tasks.map(t => [t.name, t]));
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
        nodes[skey] = { key: skey, kind: "slot", slot: dep.slot, impls: sl ? sl.impls : [], impl: sl ? (sl.default_impl || sl.impls[0]) : null };
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

// карточка слота показывает тесты и режимы выбранной реализации
const slotCard = (d, P) => P.tasks.find(t => t.name === d.impl) || null;
// «📖 библиотека · выучено» «⚙ с нуля · пора»
function modePills(statuses) {
  return MODES.map(m => {
    const st = (statuses || {})[m] || "none";
    return `<span class="mp-pill ${MS_CLS[st] || "none"}">${ICON[MODE_ICON[m]]}${MODE_NAME[m]} · ${PAIR_TEXT[st] || st}</span>`;
  }).join("");
}

// ---------------- экран конструктора ----------------
async function viewBuilder(taskId) {
  view.innerHTML = '<div class="muted spinner" style="padding:24px">загружаю конструктор</div>';
  await Promise.all([loadDrawflow(), loadMonaco()]);
  const [P, B, T] = await Promise.all([api("/api/builder/palette"), api(`/api/builder/board${taskId ? `?task_id=${taskId}` : ""}`), api("/api/builder/templates")]);
  const cards = Object.fromEntries(P.tasks.map(t => [`t:${t.id}`, t]));
  const root = B.task;
  const rootKey = root ? `t:${root.id}` : null;
  const isWall = root?.level === "wall";
  let tags = root ? [...root.tags] : [];
  document.body.classList.add("ide-mode");
  view.innerHTML = `<div class="bf-page">
    <div class="bf-top">
      <input id="bf-title" class="bf-name" placeholder="Новая задача" value="${esc(root ? root.title : "")}">
      <label class="bf-place"><span class="faint">место:</span><select id="bf-topic"><option value="">выбрать</option>${topicOptions(P.topics, root ? root.topic_id : null)}</select></label>
      <span id="bf-tags" class="row" style="gap:6px"></span>
      <span class="grow"></span>
      <span class="faint small" id="bf-status"></span>
      <button id="bf-cancel" class="link" title="вернуть сохранённую раскладку">Отмена</button>
      <button id="bf-check" class="ghost">${ICON.check}Проверить всё</button>
      <button id="bf-save" class="primary">Сохранить<kbd class="kbd-on">⌘S</kbd></button>
    </div>
    <div class="bf-cols">
      <div class="bf-palette" id="bf-palette"></div>
      <div class="bf-center" id="bf-center"><div class="bf-msg" id="bf-msg" hidden></div><div class="bf-empty" id="bf-empty" hidden></div>
        <div class="bf-selbar" id="bf-selbar" hidden></div></div>
      <div class="bf-inspector" id="bf-inspector"></div>
    </div></div>`;
  const center = $("#bf-center");
  const canvasEl = document.createElement("div");
  center.prepend(canvasEl);
  const { editor, drawMini, fit } = makeCanvas(canvasEl);
  const byKey = {}, idOf = {};  // ключ карточки <-> id узла Drawflow
  let multi = new Set(), selected = null, dirty = false, checkedAt = null, cycles = [];
  const keyOf = id => Object.keys(idOf).find(k => idOf[k] === +id);
  const cardOf = key => byKey[key]?.kind === "slot" ? slotCard(byKey[key], P) : cards[key];
  const markDirty = () => { dirty = true; renderStatus(); };
  const frameInfo = () => isWall ? { title: root.title } : null;
  const redraw = () => { drawFrame(editor, canvasEl, frameInfo()); placeSelbar(); placeCycleLabels(); requestAnimationFrame(drawMini); };

  // ---- верхняя строка: теги и состояние ----
  function renderTags() {
    $("#bf-tags").innerHTML = tags.map(t => `<span class="tag" data-tag="${esc(t)}" title="убрать">${esc(t)}</span>`).join("") + '<button class="link small" id="bf-addtag">+ тег</button>';
    $$("[data-tag]").forEach(x => x.onclick = () => { tags = tags.filter(t => t !== x.dataset.tag); renderTags(); markDirty(); });
    $("#bf-addtag").onclick = () => { const t = prompt("Тег"); if (t && !tags.includes(t.trim())) { tags.push(t.trim()); renderTags(); markDirty(); } };
  }
  renderTags();
  function renderStatus() {
    const keys = Object.keys(idOf), drafts = keys.filter(k => byKey[k].kind === "draft").length;
    const tested = keys.filter(k => Object.keys(cardOf(k)?.tests || {}).length), bad = tested.filter(k => Object.values(cardOf(k).tests).some(([p, n]) => p !== n));
    let s = !keys.length ? "пусто" : cycles.length ? "есть цикл · сохранится как черновик"
      : bad.length ? `${keys.length - bad.length} из ${keys.length} узлов проходят тесты`
      : `${keys.length} ${plural(keys.length, "узел", "узла", "узлов")}${drafts ? ` · ${drafts} ${plural(drafts, "черновик", "черновика", "черновиков")}` : ""}${checkedAt ? ` · всё проверено ${checkedAt}` : ""}`;
    if (dirty && !cycles.length) s += " · не сохранено";
    $("#bf-status").textContent = s;
    $("#bf-status").classList.toggle("err", !!cycles.length);
  }

  function addNode(d, x, y) {
    if (idOf[d.key]) return idOf[d.key];
    const card = d.kind === "slot" ? slotCard(d, P) : cards[d.key];
    if (d.kind === "task" && !card) return null;
    if (d.key === rootKey && isWall) d.wallOut = (root.main || "pipeline").replace(/\.py$/, "");
    const id = editor.addNode(d.key, d.kind === "slot" ? 0 : 1, 1, x, y, nodeClass(d, card), { key: d.key }, cardHtml(d, card));
    byKey[d.key] = d;
    idOf[d.key] = id;
    bindNode(d);
    return id;
  }
  function refreshNode(key) {
    const d = byKey[key], el = $(`#node-${idOf[key]}`);
    if (!d || !el) return;
    const c = cardOf(key);
    $(".drawflow_content_node", el).innerHTML = cardHtml(d, c);
    const keep = ["selected", "bf-multi", "bf-cycle", "bf-dim"].filter(x => el.classList.contains(x));
    el.className = `drawflow-node ${nodeClass(d, c)} ${keep.join(" ")}`;
    bindNode(d);
  }
  function bindNode(d) {
    const el = $(`#node-${idOf[d.key]}`);
    if (!el) return;
    const sel = $(".bf-impl", el);
    if (sel) {
      sel.onmousedown = e => e.stopPropagation();
      sel.onchange = () => { d.impl = sel.value; refreshNode(d.key); markDirty(); };
    }
    el.ondblclick = () => { if (arr(d.children).length) expand(d.key); };
    // упавшие тесты эталона: подсказка с первым упавшим тестом (если эталон проверяли здесь)
    el.onmouseenter = () => {
      const c = cardOf(d.key), f = c?._fails?.[0];
      if (!f) return;
      const tip = document.createElement("div");
      tip.className = "bf-tip";
      tip.innerHTML = `<b class="err">Эталон · ${esc(MODE_NAME[f.mode] || "")} не проходит свои тесты</b><div class="mono">${esc(f.name)}</div><div class="faint">${esc(f.note)}</div>`;
      el.appendChild(tip);
    };
    el.onmouseleave = () => $(".bf-tip", el)?.remove();
  }
  function edgeList() {
    const out = [];
    for (const [key, id] of Object.entries(idOf)) {
      const node = editor.getNodeFromId(id);
      for (const c of node.outputs.output_1?.connections || []) {
        const target = keyOf(c.node);
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
    multi = new Set(); cycles = [];
    if (board && arr(board.nodes).length) {
      board.nodes.forEach(n => addNode(n.data, n.x, n.y));
      arr(board.edges).forEach(e => connect(e.source, e.target));
    } else if (root) {
      const g = depGraph(P.tasks.find(t => t.id === root.id), P);
      const pos = autoLayout(g.keys, g.edges);
      g.keys.forEach(k => addNode(g.nodes[k], pos[k].x, pos[k].y));
      g.edges.forEach(e => connect(e.source, e.target));
    }
    dirty = false;
    showEmpty();
    renderStatus();
    inspect(null);
    setTimeout(() => { redraw(); if (Object.keys(idOf).length) fit(); }, 30);
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
    showMsg.t = setTimeout(() => { m.hidden = true; }, 5000);
  }
  // пустой холст — шаблоны (стр. 6)
  function showEmpty() {
    const box = $("#bf-empty"), empty = !Object.keys(idOf).length;
    box.hidden = !empty;
    if (!empty) return;
    box.innerHTML = `<h2>Пустой холст</h2><p class="muted">Начни с шаблона или перетащи кирпичик из палитры слева</p>
      <div class="tpl-grid">${Object.keys(T).map(k => { const [t, sig, txt, c] = TPL_INFO[k] || [T[k].title, "", "", ""];
        return `<button class="tpl ${c}" data-tpl="${k}" draggable="true"><b><i></i>${esc(t)}</b><span class="mono faint">${esc(sig)}</span><span>${esc(txt)}</span></button>`; }).join("")}</div>`;
    $$("[data-tpl]", box).forEach(b => {
      b.onclick = () => { const r = canvasEl.getBoundingClientRect(); dropWhat(`tpl:${b.dataset.tpl}`, r.left + r.width / 2 - 90, r.top + r.height / 2 - 40); };
      b.ondragstart = e => e.dataTransfer.setData("text/bf", `tpl:${b.dataset.tpl}`);
    });
  }

  // ---- циклы: стрелка остаётся красной с подписью, пока её не удалят или не развернут ----
  function depsOf(key) {
    const d = byKey[key];
    const fromBoard = edgeList().filter(e => e.target === key).map(e => e.source);
    if (d?.kind !== "task") return fromBoard;
    const byName = Object.fromEntries(P.tasks.map(x => [x.name, x]));
    const known = arr(cards[key]?.deps).map(dep => dep.task && byName[dep.task] ? `t:${byName[dep.task].id}` : null).filter(Boolean);
    return [...new Set([...fromBoard, ...known])];
  }
  function findPath(from, to, seen = new Set(), skip = null) {  // путь по «использует»: from -> … -> to
    if (from === to) return [from];
    if (seen.has(from)) return null;
    seen.add(from);
    for (const dep of depsOf(from)) {
      if (skip && from === skip.target && dep === skip.source) continue;  // без самой проверяемой стрелки
      const p = findPath(dep, to, seen, skip);
      if (p) return [from, ...p];
    }
    return null;
  }
  const nameOf = key => byKey[key]?.kind === "slot" ? `слот ${byKey[key].slot}` : cardOf(key)?.name || byKey[key]?.title || key;
  const connEl = (src, dst) => $(`.connection.node_out_node-${idOf[src]}.node_in_node-${idOf[dst]}`, canvasEl);
  function recheckCycles() {
    // зависимость, уже сохранённая в задаче, не «новая»: красной делаем только стрелку, проведённую на холсте
    const saved = e => { const t = cards[e.target], src = byKey[e.source];
      return !!t && arr(t.deps).some(x => src?.kind === "slot" ? x.slot === src.slot : x.task && x.task === cards[e.source]?.name); };
    cycles = edgeList().filter(e => !saved(e)).map(e => ({ ...e, path: findPath(e.source, e.target, new Set(), e) })).filter(e => e.path)
      .map(e => ({ source: e.source, target: e.target, text: [...e.path, e.source].map(nameOf).join(" → ") }));
    $$(".bf-cyc", canvasEl).forEach(x => x.classList.remove("bf-cyc"));
    $$(".drawflow-node.bf-cycle", canvasEl).forEach(x => x.classList.remove("bf-cycle"));
    $$(".input.bf-port-cyc", canvasEl).forEach(x => x.classList.remove("bf-port-cyc"));
    for (const c of cycles) {
      connEl(c.source, c.target)?.classList.add("bf-cyc");
      [c.source, c.target].forEach(k => $(`#node-${idOf[k]}`)?.classList.add("bf-cycle"));
      $(`#node-${idOf[c.target]} .input`, canvasEl)?.classList.add("bf-port-cyc");
    }
    placeCycleLabels();
    renderStatus();
  }
  function placeCycleLabels() {
    $$(".bf-cyc-label", editor.precanvas).forEach(x => x.remove());
    for (const c of cycles) {
      const a = editor.getNodeFromId(idOf[c.source]), b = editor.getNodeFromId(idOf[c.target]);
      if (!a || !b) continue;
      const w = $(`#node-${idOf[c.source]}`)?.offsetWidth || 170;
      const lab = document.createElement("button");
      lab.className = "bf-cyc-label";
      lab.innerHTML = `↻ Цикл: ${esc(c.text)}`;
      Object.assign(lab.style, { left: `${(a.pos_x + w + b.pos_x) / 2}px`, top: `${(a.pos_y + b.pos_y) / 2 + 30}px` });
      lab.onclick = () => inspectLink(c.source, c.target);
      editor.precanvas.appendChild(lab);
    }
  }
  editor.on("connectionCreated", ({ output_id, input_id }) => {
    const src = keyOf(output_id), dst = keyOf(input_id);
    if (byKey[dst]?.kind === "slot") {
      editor.removeSingleConnection(output_id, input_id, "output_1", "input_1");
      return showMsg("слот ничего не использует: стрелка ведёт от кирпичика к тому, кто его использует");
    }
    recheckCycles();
    if (cycles.some(c => c.source === src && c.target === dst)) inspectLink(src, dst);
    markDirty();
  });
  editor.on("connectionRemoved", () => { recheckCycles(); markDirty(); });
  editor.on("connectionSelected", ({ output_id, input_id }) => inspectLink(keyOf(output_id), keyOf(input_id)));
  // пока тянется стрелка: порты, куда можно отпустить, и порты, где получится цикл
  editor.on("connectionStart", ({ output_id }) => {
    const src = keyOf(output_id);
    for (const k of Object.keys(idOf)) {
      const port = $(`#node-${idOf[k]} .input`, canvasEl);
      if (!port || k === src) continue;
      port.classList.add(findPath(src, k) ? "bf-port-cyc" : "bf-port-ok");
    }
  });
  const clearPorts = () => $$(".bf-port-ok, .input.bf-port-cyc", canvasEl).forEach(p => p.classList.remove("bf-port-ok", "bf-port-cyc"));
  editor.on("connectionCancel", () => { clearPorts(); recheckCycles(); });
  editor.on("connectionCreated", () => { clearPorts(); recheckCycles(); });
  editor.on("nodeMoved", () => { markDirty(); redraw(); });
  editor.on("nodeRemoved", id => {
    const key = keyOf(id);
    if (key) { delete idOf[key]; delete byKey[key]; multi.delete(key); }
    recheckCycles(); markDirty(); showEmpty(); redraw();
  });
  editor.on("nodeSelected", id => {
    const key = keyOf(id);
    if (window.event?.shiftKey) {  // Shift + клик — множественный выбор для «Собрать в блок»
      if (selected && !multi.size) multi.add(selected);
      multi.has(key) ? multi.delete(key) : multi.add(key);
      paintMulti();
      return;
    }
    multi = new Set(); paintMulti();
    selected = key;
    inspect(key);
  });
  function paintMulti() {
    $$(".bf-multi", canvasEl).forEach(e => e.classList.remove("bf-multi"));
    multi.forEach(k => $(`#node-${idOf[k]}`)?.classList.add("bf-multi"));
    placeSelbar();
    if (multi.size > 1) inspectMulti();
  }
  // панель над выделением: «N выбрано · Собрать в блок ⌘G · Выровнять» (стр. 7)
  function placeSelbar() {
    const bar = $("#bf-selbar");
    const keys = [...multi].filter(k => idOf[k]);
    let box = $(".bf-selbox", editor.precanvas);
    if (keys.length < 2) { bar.hidden = true; box?.remove(); return; }
    const ns = keys.map(k => [editor.getNodeFromId(idOf[k]), $(`#node-${idOf[k]}`)]);
    const minX = Math.min(...ns.map(([n]) => n.pos_x)) - 10, minY = Math.min(...ns.map(([n]) => n.pos_y)) - 10;
    const maxX = Math.max(...ns.map(([n, el]) => n.pos_x + el.offsetWidth)) + 10, maxY = Math.max(...ns.map(([n, el]) => n.pos_y + el.offsetHeight)) + 10;
    if (!box) { box = document.createElement("div"); box.className = "bf-selbox"; editor.precanvas.appendChild(box); }
    Object.assign(box.style, { left: `${minX}px`, top: `${minY}px`, width: `${maxX - minX}px`, height: `${maxY - minY}px` });
    bar.hidden = false;
    bar.innerHTML = `<span class="faint">${keys.length} выбрано</span><button class="primary small" data-sb="block">Собрать в блок<kbd class="kbd-on">⌘G</kbd></button><button class="link small" data-sb="align">Выровнять</button>`;
    const r = box.getBoundingClientRect(), c = center.getBoundingClientRect();
    Object.assign(bar.style, { left: `${Math.max(8, r.left - c.left)}px`, top: `${Math.max(8, r.top - c.top - 40)}px` });
    $("[data-sb=block]", bar).onclick = () => makeBlock();
    $("[data-sb=align]", bar).onclick = () => {  // в столбик по левому краю, с шагом по высоте
      const x = Math.min(...ns.map(([n]) => n.pos_x));
      let y = Math.min(...ns.map(([n]) => n.pos_y));
      ns.sort((a, b) => a[0].pos_y - b[0].pos_y).forEach(([n, el]) => {
        n.pos_x = x; n.pos_y = y; el.style.left = `${x}px`; el.style.top = `${y}px`; editor.updateConnectionNodes(`node-${n.id}`); y += el.offsetHeight + 24;
      });
      markDirty(); redraw();
    };
  }
  const onKey = e => {
    if (!document.body.contains(canvasEl)) return document.removeEventListener("keydown", onKey);
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); $("#bf-save").click(); }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "g" && multi.size > 1) { e.preventDefault(); makeBlock(); }
  };
  document.addEventListener("keydown", onKey);

  // ---- палитра: «Дерево тем» / «Карта», поиск ----
  const palette = $("#bf-palette");
  let tab = store.get("bf.tab", "tree") === "map" ? "map" : "tree", q = "";
  const collapsedGroups = new Set(store.get("bf.groups", []));
  function renderPalette() {
    const ql = q.toLowerCase(), match = t => !ql || (t.name + " " + t.title + " " + t.tags.join(" ")).toLowerCase().includes(ql);
    const onBoard = k => !!idOf[k];
    const item = t => `<div class="pal-item ${onBoard(`t:${t.id}`) ? "on" : ""}" draggable="true" data-drag="t:${t.id}" title="${esc(t.title)}"><span class="mono">${esc(t.name)}</span><span class="grow"></span>${modeHalves(t.statuses)}</div>`;
    let body = "";
    if (tab === "tree") {
      const topicName = Object.fromEntries(P.topics.map(x => [x.id, x.name]));
      const groups = {};
      P.tasks.filter(match).forEach(t => (groups[topicName[t.topic_id] || "Без темы"] ||= []).push(t));
      const drafts = Object.values(byKey).filter(d => d.kind === "draft" && (!ql || d.title.toLowerCase().includes(ql)));
      body = Object.entries(groups).sort(([a], [b]) => a.localeCompare(b)).map(([g, list]) => {
        const open = !collapsedGroups.has(g) || ql;
        return `<div class="pal-group ${catClass(g)}"><button class="pal-gh" data-grp="${esc(g)}"><span class="caret">${open ? "⌄" : "›"}</span><i></i><b>${esc(g)}</b><span class="grow"></span><span class="faint">${list.length}</span></button>
          ${open ? list.map(item).join("") : ""}</div>`;
      }).join("") + (drafts.length ? `<div class="pal-group"><div class="pal-gh"><span class="caret"></span><b>Черновики на холсте</b></div>${drafts.map(d => `<div class="pal-item"><span class="mono">${esc(d.title)}</span><span class="grow"></span><span class="faint small">черновик</span></div>`).join("")}</div>` : "");
      const sl = P.slots.filter(s => !ql || (s.name + " " + s.title).toLowerCase().includes(ql));
      if (sl.length) body += `<div class="pal-group"><div class="pal-gh"><span class="caret"></span><b>Слоты</b><span class="grow"></span><span class="faint">${sl.length}</span></div>
        ${sl.map(s => `<div class="pal-item" draggable="true" data-drag="s:${esc(s.name)}" title="${esc(s.signature || "")}"><span class="mono">слот · ${esc(s.name)}</span></div>`).join("")}</div>`;
    } else {
      const byName = Object.fromEntries(P.tasks.map(t => [t.name, t]));
      body = P.map_rows.map(r => {
        const list = r.bricks.filter(b => !ql || b.toLowerCase().includes(ql));
        if (!list.length) return "";
        return `<div class="pal-group"><div class="pal-gh"><span class="caret"></span><b>${esc(r.title)}</b><span class="grow"></span><span class="faint">${list.length}</span></div>
          ${list.map(b => byName[b] ? item(byName[b]) : `<div class="pal-item planned" draggable="true" data-drag="planned:${esc(b)}" title="задачи ещё нет — перетащите, будет черновик"><span class="mono">${esc(b)}</span><span class="grow"></span><span class="faint small">план</span>${modeHalves({})}</div>`).join("")}</div>`;
      }).join("");
    }
    palette.innerHTML = `<div class="seg pal-tabs">${[["tree", "Дерево тем"], ["map", "Карта"]].map(([k, n]) => `<button data-ptab="${k}" class="${k === tab ? "sel" : ""}">${n}</button>`).join("")}</div>
      <label class="pal-search">${ICON.search}<input id="bf-q" placeholder="Найти кирпичик" value="${esc(q)}"></label>
      <div class="pal-body">${body || '<p class="faint small" style="padding:8px">ничего не найдено</p>'}</div>
      <div class="pal-tpls"><div class="label">Шаблоны</div>${Object.keys(T).map(k => `<div class="pal-item tpl-mini ${(TPL_INFO[k] || [])[3] || ""}" draggable="true" data-drag="tpl:${k}"><i></i>${esc((TPL_INFO[k] || [T[k].title])[0])}</div>`).join("")}</div>`;
    $$("[data-ptab]", palette).forEach(b => b.onclick = () => { tab = b.dataset.ptab; store.set("bf.tab", tab); renderPalette(); });
    $$("[data-grp]", palette).forEach(b => b.onclick = () => { const g = b.dataset.grp; collapsedGroups.has(g) ? collapsedGroups.delete(g) : collapsedGroups.add(g); store.set("bf.groups", [...collapsedGroups]); renderPalette(); });
    const qi = $("#bf-q", palette);
    qi.oninput = () => { q = qi.value; renderPalette(); const n = $("#bf-q", palette); n.focus(); n.setSelectionRange(n.value.length, n.value.length); };
    $$("[data-drag]", palette).forEach(el => {
      el.ondragstart = e => { e.dataTransfer.setData("text/bf", el.dataset.drag); el.classList.add("dragging"); };
      el.ondragend = () => { el.classList.remove("dragging"); guide(null); };
    });
  }
  renderPalette();

  // ---- перетаскивание из палитры: направляющая к ближайшему входу и подсказка «отпусти → вход X» (стр. 10) ----
  const toWorld = (cx, cy) => {
    const pre = editor.precanvas.getBoundingClientRect();
    return { x: (cx - pre.x) / editor.zoom, y: (cy - pre.y) / editor.zoom };
  };
  let guideTarget = null;
  function guide(pt) {
    $$(".bf-guide, .bf-drophint", editor.precanvas).forEach(x => x.remove());
    $$(".bf-port-ok", canvasEl).forEach(p => p.classList.remove("bf-port-ok"));
    guideTarget = null;
    if (!pt) return;
    let best = null;
    for (const [k, id] of Object.entries(idOf)) {
      if (byKey[k].kind === "slot") continue;
      const n = editor.getNodeFromId(id), h = $(`#node-${id}`)?.offsetHeight || 64;
      const dx = n.pos_x - pt.x, dy = n.pos_y + h / 2 - pt.y, dist = Math.hypot(dx, dy);
      if (dist < 220 && (!best || dist < best.dist)) best = { k, dist, x: n.pos_x, y: n.pos_y + h / 2, id };
    }
    if (!best) return;
    guideTarget = best.k;
    $(`#node-${best.id} .input`, canvasEl)?.classList.add("bf-port-ok");
    const svgNS = "http://www.w3.org/2000/svg", s = document.createElementNS(svgNS, "svg");
    s.setAttribute("class", "bf-guide");
    const x1 = pt.x, y1 = pt.y, x2 = best.x, y2 = best.y, m = (x1 + x2) / 2;
    s.innerHTML = `<path d="M${x1},${y1} C${m},${y1} ${m},${y2} ${x2},${y2}"/>`;
    editor.precanvas.appendChild(s);
    const hint = document.createElement("div");
    hint.className = "bf-drophint";
    hint.textContent = `отпусти → вход ${nameOf(best.k)}`;
    Object.assign(hint.style, { left: `${pt.x}px`, top: `${pt.y + 40}px` });
    editor.precanvas.appendChild(hint);
  }
  canvasEl.ondragover = e => { e.preventDefault(); guide(toWorld(e.clientX, e.clientY)); };
  canvasEl.ondragleave = e => { if (!canvasEl.contains(e.relatedTarget)) guide(null); };
  let draftN = 0;
  canvasEl.ondrop = e => { e.preventDefault(); const what = e.dataTransfer.getData("text/bf"); const target = guideTarget; guide(null); if (what) dropWhat(what, e.clientX, e.clientY, target); };
  function dropWhat(what, cx, cy, target = null) {
    const { x, y } = toWorld(cx, cy);
    let key = null;
    if (what.startsWith("t:")) {
      if (idOf[what]) return showMsg("эта карточка уже на холсте", "muted");
      key = what;
      addNode({ key: what, kind: "task", task_id: +what.slice(2) }, x, y);
      const g = depGraph(cards[what], P);  // её зависимости — тоже на холст, со стрелками (иначе при сохранении они бы потерялись)
      const pos = autoLayout(g.keys, g.edges);
      g.keys.forEach(kk => addNode(g.nodes[kk], x + pos[kk].x - pos[what].x, y + pos[kk].y - pos[what].y));
      g.edges.forEach(ed => { if (!edgeList().some(x2 => x2.source === ed.source && x2.target === ed.target)) connect(ed.source, ed.target); });
    } else if (what.startsWith("s:")) {
      const sl = P.slots.find(s => s.name === what.slice(2));
      key = what;
      addNode({ key: what, kind: "slot", slot: sl.name, impls: sl.impls, impl: sl.default_impl || sl.impls[0] }, x, y);
    } else {
      const tplKey = what.startsWith("tpl:") ? what.slice(4) : "sklearn_function";
      const tpl = T[tplKey];
      const title = what.startsWith("planned:") ? what.slice(8) : `${(TPL_INFO[tplKey] || [tpl.title])[0]} ${++draftN}`;
      key = `d:${Date.now().toString(36)}${draftN}`;
      addNode({ key, kind: "draft", level: tpl.level, title, files: { ...tpl.files }, meta: { ...tpl.meta }, implements: tpl.implements, main: tpl.main,
                category: { c_pre: "preprocessing", c_lay: "layers", c_met: "metrics", c_mod: "models" }[((TPL_INFO[tplKey] || [])[3] || "").replace("-", "_")] || "",
                topic_id: $("#bf-topic").value ? +$("#bf-topic").value : null, tags: [] }, x, y);
      selected = key;
      inspect(key);
    }
    if (key && target && byKey[target]?.kind !== "slot" && key !== target) connect(key, target);
    showEmpty(); markDirty(); renderPalette(); recheckCycles(); redraw();
  }

  // ---- «Собрать в блок» и раскрытие ----
  async function makeBlock(title, topicId) {
    const members = [...multi].filter(k => byKey[k]);
    if (members.length < 2) return showMsg("выделите карточки: Shift + клик по каждой", "muted");
    if (members.some(k => byKey[k].kind === "draft")) return showMsg("черновики сначала сохраните («Сохранить»), потом собирайте в блок");
    title = title || $("#bf-blockname")?.value.trim() || prompt("Имя блока", "новый блок");
    if (!title) return;
    try {
      const card = await api("/api/builder/block", { method: "POST", json: { title, members, topic_id: topicId ?? ($("#bf-topic").value ? +$("#bf-topic").value : null),
        tags: ["блок", ...tags.filter(t => !["стена", "блок"].includes(t))] } });
      P.tasks.push(card);
      cards[`t:${card.id}`] = card;
      const pos = members.map(k => editor.getNodeFromId(idOf[k]));
      const cx = Math.max(...pos.map(p => p.pos_x)) + 240, cy = pos.reduce((s, p) => s + p.pos_y, 0) / pos.length;
      const children = members.map(k => ({ data: byKey[k], x: editor.getNodeFromId(idOf[k]).pos_x, y: editor.getNodeFromId(idOf[k]).pos_y }));
      const outer = edgeList().filter(e => members.includes(e.source) && !members.includes(e.target));  // кто использовал выбранные
      members.forEach(k => editor.removeNodeId(`node-${idOf[k]}`));
      const key = `t:${card.id}`;
      addNode({ key, kind: "task", task_id: card.id, children }, cx, cy);
      outer.forEach(e => connect(key, e.target));
      multi = new Set(); paintMulti();
      markDirty();
      toast(`блок «${card.title}» создан — зависимости: ${card.deps.map(d => d.name).join(", ")}`);
      selected = key; inspect(key); renderPalette(); redraw();
    } catch (e) { showMsg(e.message); }
  }
  function expand(key) {  // двойной клик по свёрнутому блоку: вернуть карточки и стрелки в блок
    const d = byKey[key];
    d.children.forEach(c => addNode(c.data, c.x, c.y));
    d.children.forEach(c => connect(c.data.key, key));
    d.children = [];
    refreshNode(key);
    markDirty(); redraw();
  }

  // ---- инспектор ----
  const insp = $("#bf-inspector");
  function disposeEd() { if (insp._ed) { insp._ed.dispose(); insp._ed = null; } }
  function inspectMulti() {
    disposeEd();
    const keys = [...multi];
    insp.innerHTML = `<div class="label">Выделено</div><h2 class="insp-h">${keys.length} ${plural(keys.length, "кирпичик", "кирпичика", "кирпичиков")}</h2>
      <div class="insp-list">${keys.map(k => `<div class="${catClass(cardOf(k)?.category)}"><i class="sq"></i><span class="mono">${esc(nameOf(k))}</span></div>`).join("")}</div>
      <div class="insp-sep"></div><div class="label">Собрать в блок</div>
      <label class="fld">Имя блока<input id="bf-blockname" placeholder="например conv_block"></label>
      <label class="fld">Место в дереве<select id="bf-blocktopic"><option value="">как у задачи</option>${topicOptions(P.topics, null)}</select></label>
      <p class="muted small">Выбранные карточки станут зависимостями новой задачи-блока и свернутся в одну карточку; двойной клик раскрывает. Заготовки — для обоих режимов, тесты блока добавишь потом.</p>
      <button class="primary wide" id="bf-doblock">Собрать в блок<kbd class="kbd-on">⌘G</kbd></button>`;
    $("#bf-doblock").onclick = () => makeBlock($("#bf-blockname").value.trim(), $("#bf-blocktopic").value ? +$("#bf-blocktopic").value : undefined);
  }
  function inspectLink(src, dst) {
    disposeEd();
    if (!src || !dst) return;
    const cyc = cycles.find(c => c.source === src && c.target === dst);
    insp.innerHTML = `<div class="label">Связь</div><div class="mono insp-link">${esc(nameOf(src))} <span class="faint">→</span> ${esc(nameOf(dst))}</div>
      <p class="muted small">${esc(nameOf(dst))} использует ${esc(nameOf(src))}: при сохранении станет зависимостью.</p>
      ${cyc ? `<div class="alert err"><b>Эта связь замыкает цикл</b><p>${esc(nameOf(src))} уже ${byKey[src]?.kind === "slot" ? "" : "(через цепочку) "}использует ${esc(nameOf(dst))}: ${esc(cyc.text)}.
        Если ${esc(nameOf(dst))} станет зависимостью ${esc(nameOf(src))}, задачу нельзя будет собрать и повторять по порядку.</p></div>` : ""}
      <div class="row mt"><button class="danger" id="bf-unlink">Удалить связь</button>${cyc ? '<button id="bf-flip">Развернуть направление</button>' : ""}</div>
      ${cyc ? '<p class="muted small mt">Пока цикл есть, «Сохранить» сохраняет только раскладку — зависимости задач не меняются.</p>' : ""}`;
    $("#bf-unlink").onclick = () => { editor.removeSingleConnection(idOf[src], idOf[dst], "output_1", "input_1"); inspect(null); };
    const flip = $("#bf-flip");
    if (flip) flip.onclick = () => {
      editor.removeSingleConnection(idOf[src], idOf[dst], "output_1", "input_1");
      if (byKey[src]?.kind === "slot") return showMsg("слот не может ничего использовать — связь удалена");
      connect(dst, src); inspect(null);
    };
  }
  async function inspect(key) {
    disposeEd();
    const d = key && byKey[key];
    if (!d) {
      insp.innerHTML = emptyState({ icon: "panel", title: "Ничего не выбрано", text: "Выбери карточку — здесь появятся README, эталоны для двух режимов, тесты и data/.",
        actions: '<a class="btn" href="#/settings">Импорт из combinations.csv</a>' });
      return;
    }
    if (d.kind === "slot") {
      const sl = P.slots.find(s => s.name === d.slot) || {}, impl = slotCard(d, P);
      insp.innerHTML = `<div class="insp-head"><b class="mono">слот · ${esc(d.slot)}</b></div><p class="mono small faint">${esc(sl.signature || "")}</p>
        <div class="label mt">Реализации</div><div class="chips">${arr(sl.impls).map(i => `<span class="chip-n ${i === d.impl ? "sel" : ""}">${esc(i)}</span>`).join("")}</div>
        ${impl ? `<div class="label mt">Выбрана</div><div class="row">${modePills(impl.statuses)}</div><button class="mt" id="bf-open-impl">Открыть ${esc(impl.name)}</button>` : ""}
        <p class="muted small mt">Реализация выбирается на карточке; при старте составной задачи её можно сменить на экране сборки.</p>`;
      const oi = $("#bf-open-impl");
      if (oi) oi.onclick = () => { location.hash = `#/task/${impl.id}`; };
      return;
    }
    const isTask = d.kind === "task", card = cards[key] || {};
    const modes = isTask ? card.modes : MODES;
    const lvl = isTask ? (card.level || "brick") : d.level || "brick";
    let cur = insp._tab && (insp._tab !== "library" || modes.includes("library")) && (insp._tab !== "scratch" || modes.includes("scratch")) ? insp._tab : (modes[0] || "readme");
    const testsLabel = card._check ? `${card._check.passed}/${card._check.total}` : (() => { const t = Object.values(card.tests || {}); return t.length ? `${Math.min(...t.map(x => x[0]))}/${t[0][1]}` : ""; })();
    const tabs = [["readme", "README"], ...modes.map(m => [m, `${ICON[MODE_ICON[m]]}Эталон`]), ["tests", `Тесты${testsLabel ? ` <span class="faint">${testsLabel}</span>` : ""}`], ["data", "data/"]];
    const usedBoard = edgeList().filter(e => e.source === key).map(e => e.target);
    insp.innerHTML = `<div class="insp-head"><b class="mono">${esc(isTask ? card.name : d.title)}</b>${levelTag(lvl)}<span class="grow"></span>${catTag(isTask ? card.category : d.category)}</div>
      ${isTask ? `<div class="row insp-modes">${modePills(card.statuses)}</div>` : `<input id="bf-dtitle" value="${esc(d.title)}" style="width:100%;margin-top:8px"><div class="faint small mt">черновик — станет задачей при «Сохранить»</div>`}
      <div class="tabs insp-tabs">${tabs.map(([k, n]) => `<button data-itab="${k}" class="${k === cur ? "active" : ""}">${n}</button>`).join("")}</div>
      <div id="bf-ibody"></div>
      <div class="insp-foot"><div class="label">Где используется</div><div class="chips" id="bf-iused">${usedBoard.map(k => `<span class="chip-n">${esc(nameOf(k))}</span>`).join("") || '<span class="faint small">на холсте стрелок отсюда нет</span>'}</div></div>`;
    if (isTask) {
      const users = P.tasks.filter(t => arr(t.deps).some(x => x.task === card.name) && !usedBoard.includes(`t:${t.id}`));
      if (users.length) $("#bf-iused").insertAdjacentHTML("beforeend", users.map(t => `<a class="chip-n" href="#/task/${t.id}">${esc(t.name)}</a>`).join(""));
    }
    const dt = $("#bf-dtitle", insp);
    if (dt) dt.oninput = () => { d.title = dt.value; refreshNode(key); markDirty(); };
    $$("[data-itab]", insp).forEach(b => b.onclick = () => { insp._tab = b.dataset.itab; inspect(key); });
    const ib = $("#bf-ibody", insp);
    const listFiles = async dir => { try { return await api(`/api/tasks/${card.id}/files?path=${encodeURIComponent(dir)}`); } catch { return []; } };
    const readFile = async path => isTask ? (await api(`/api/tasks/${card.id}/file?path=${encodeURIComponent(path)}`).catch(() => ({ content: "" }))).content : (d.files || {})[path] || "";
    const writeFile = async (path, text) => {
      if (isTask) { await api(`/api/tasks/${card.id}/file`, { method: "PUT", json: { path, content: text } }); toast(`${path} записан — «Сохранить версию» в редакторе задачи`); }
      else { d.files = { ...d.files, [path]: text }; markDirty(); }
    };
    let meta = {};
    if (isTask) { try { meta = JSON.parse(await readFile("task.json") || "{}"); } catch { meta = {}; } } else meta = d.meta || (d.meta = {});
    const saveMeta = async () => { if (isTask) await writeFile("task.json", JSON.stringify(meta, null, 2) + "\n"); else { d.meta = meta; markDirty(); } };

    // «Проверить эталон · режим»: результат строкой «✓ 9/9 · 1.4 с»
    const checkRow = ms => `<div class="row mt">${ms.map(m => `<button data-icheck="${m}" ${isTask ? "" : 'disabled title="сначала сохраните черновик"'}>Проверить эталон · ${MODE_NAME[m]}</button><span class="small" data-ires="${m}">${card._res?.[m] || ""}</span>`).join("")}</div>`;
    const runCheck = async mode => {
      const res = $(`[data-ires="${mode || "all"}"]`, insp) || $(`[data-ires="${mode}"]`, insp);
      if (res) res.innerHTML = '<span class="faint spinner">проверяю</span>';
      const t0 = Date.now();
      const { job } = await api(`/api/tasks/${card.id}/check${mode ? `?mode=${mode}` : ""}`, { method: "POST" });
      const r = (await followJob(job, () => {})).result.check;
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      card.tests = { ...card.tests, ...Object.fromEntries(Object.entries(r.modes || {}).map(([m, v]) => [m, [v.passed, v.total]])) };
      card._res = { ...card._res, ...Object.fromEntries(Object.entries(r.modes || {}).map(([m, v]) => [m, `<span class="${v.passed === v.total ? "ok" : "err"}">${v.passed === v.total ? "✓" : "✗"} ${v.passed}/${v.total} · ${secs} с</span>`])) };
      card._fails = r.tests.filter(t => ["fail", "error"].includes(t.status)).map(t => { const eg = expectedGot(t.message, t.text); return { name: t.name, mode: t.mode, note: eg ? `ожидалось ${eg.expected}, получено ${eg.got}` : (t.message || "").split("\n")[0].slice(0, 120) }; });
      if (!mode) card._check = r;
      refreshNode(key); renderStatus();
      return r;
    };
    const bindChecks = () => $$("[data-icheck]", insp).forEach(b => b.onclick = async () => { b.disabled = true; await runCheck(b.dataset.icheck); b.disabled = false; inspect(key); });

    // обязательные и запрещённые имена — чипами (task.json)
    const namesHtml = () => `<div class="label mt">Обязательные имена <span class="faint">(режим «Библиотека»)</span></div>
      <div class="chips">${arr(meta.required_names).map(n => `<span class="chip-n" data-rm="required_names" data-v="${esc(n)}" title="убрать">${esc(n)}</span>`).join("")}<button class="chip-add" data-add="required_names">+ добавить</button></div>
      <div class="label mt">Запрещённые имена <span class="faint">(режим «С нуля»)</span></div>
      <div class="chips">${arr(meta.forbidden_names).map(n => `<span class="chip-n bad" data-rm="forbidden_names" data-v="${esc(n)}" title="убрать">${esc(n)}</span>`).join("")}<button class="chip-add" data-add="forbidden_names">+ добавить</button></div>
      <details class="mt"><summary class="faint small">ещё поля task.json</summary>
        ${[["library_function", "library_function"], ["signature", "сигнатура"]].map(([k, n]) => `<label class="fld">${n}<input data-mf="${k}" value="${esc(meta[k] || "")}"></label>`).join("")}
        <label class="fld">forbidden_modules<input data-mf="forbidden_modules" value="${esc(arr(meta.forbidden_modules).join(", "))}"></label>
        <label class="fld">required_kwargs — {"функция": ["параметр"]}<textarea data-mf="required_kwargs" class="mono" rows="2">${esc(JSON.stringify(meta.required_kwargs || {}))}</textarea></label>
        <button class="small" id="bf-msave">Записать поля</button></details>`;
    const bindNames = () => {
      $$("[data-rm]", ib).forEach(c => c.onclick = async () => { meta[c.dataset.rm] = arr(meta[c.dataset.rm]).filter(x => x !== c.dataset.v); await saveMeta(); inspect(key); });
      $$("[data-add]", ib).forEach(b => b.onclick = async () => { const v = prompt("Имя"); if (!v) return; meta[b.dataset.add] = [...arr(meta[b.dataset.add]), v.trim()]; await saveMeta(); inspect(key); });
      const ms = $("#bf-msave", ib);
      if (ms) ms.onclick = async () => {
        for (const el of $$("[data-mf]", ib)) {
          const k = el.dataset.mf, v = el.value.trim();
          if (k === "required_kwargs") { try { meta[k] = v ? JSON.parse(v) : {}; } catch { return toast("required_kwargs — не JSON", true); } }
          else if (k === "forbidden_modules") meta[k] = v.split(",").map(s => s.trim()).filter(Boolean);
          else meta[k] = v;
        }
        await saveMeta(); toast("поля task.json записаны");
      };
    };
    const editorIn = async (host, path, lang) => {
      const text = await readFile(path);
      insp._ed = monaco.editor.create(host, { value: text, language: lang, automaticLayout: true, minimap: { enabled: false }, fontSize: 12.5, lineNumbersMinChars: 3,
        fontFamily: "JetBrains Mono, Menlo, monospace", fontLigatures: false, scrollBeyondLastLine: false, wordWrap: "on", padding: { top: 8 } });
      insp._path = path;
      insp._ed.onDidBlurEditorText(() => { const v = insp._ed?.getValue(); if (v != null && v !== text) writeFile(path, v); });
    };

    if (cur === "readme") {
      ib.innerHTML = `<div class="insp-code" id="bf-code"></div>${namesHtml()}${checkRow(modes)}`;
      await editorIn($("#bf-code", ib), "description.md", "markdown");
      bindNames(); bindChecks();
    } else if (MODES.includes(cur)) {
      const prefix = `reference/${cur}/`;
      let paths = isTask ? (await (async () => { const out = []; const walk = async dir => { for (const f of await listFiles(dir)) f.dir ? await walk(f.path) : out.push(f.path); }; await walk(prefix.slice(0, -1)); return out; })())
        : Object.keys(d.files || {}).filter(p => p.startsWith(prefix));
      if (!paths.length && cur === "scratch" && isTask) paths = (await listFiles("reference")).filter(f => !f.dir).map(f => f.path);
      const main = paths.find(p => p.endsWith(`/${card.main || meta.main || "solution.py"}`)) || paths[0] || `${prefix}solution.py`;
      ib.innerHTML = `${paths.length > 1 ? `<select id="bf-file" class="small" style="width:100%;margin-bottom:6px">${paths.map(p => `<option ${p === main ? "selected" : ""}>${esc(p)}</option>`).join("")}</select>` : `<div class="faint small mono" style="margin-bottom:6px">${esc(main)}</div>`}
        <div class="insp-code" id="bf-code"></div>${namesHtml()}${checkRow([cur])}`;
      await editorIn($("#bf-code", ib), main, "python");
      const sel = $("#bf-file", ib);
      if (sel) sel.onchange = async () => { disposeEd(); await editorIn($("#bf-code", ib), sel.value, "python"); };
      bindNames(); bindChecks();
    } else if (cur === "tests") {
      // прогон тестов на обоих эталонах — две колонки галочек (стр. 9)
      const r = card._check;
      const failText = card._check ? Object.entries(r.modes || {}).filter(([, v]) => v.passed !== v.total).map(([m, v]) => `Эталон · ${MODE_NAME[m]} не проходит ${v.total - v.passed} из ${v.total} тестов — поправьте эталон или тесты.`) : [];
      const byName = {};
      arr(r?.tests).forEach(t => { (byName[t.name] ||= { file: t.file, res: {} }).res[t.mode] = t; });
      const files = isTask ? (await listFiles("tests")).filter(f => !f.dir).map(f => f.path) : Object.keys(d.files || {}).filter(p => p.startsWith("tests/"));
      ib.innerHTML = `${failText.map(t => `<div class="alert err">${esc(t)}</div>`).join("")}
        <div class="t2-head"><span class="mono faint">${esc(files.filter(f => f.endsWith(".py") && !f.includes("likelib")).join(", ") || "tests/")}</span><span class="grow"></span><span class="faint small">прогон на эталоне:</span>
          ${modes.map(m => `<span class="mi mi-${m === "library" ? "lib" : "scr"}" title="${MODE_TITLE[m]}">${ICON[MODE_ICON[m]]}</span>`).join("")}</div>
        ${r ? Object.entries(byName).map(([n, x]) => {
          const bad = Object.values(x.res).find(t => ["fail", "error"].includes(t.status)), eg = bad && expectedGot(bad.message, bad.text);
          return `<div class="t2-row"><div class="grow"><div class="mono">${esc(n)}</div>${bad ? `<div class="err small">${esc(eg ? `ожидалось ${eg.expected}, получено ${eg.got}` : (bad.message || "").split("\n")[0].slice(0, 140))}</div>` : ""}</div>
            ${modes.map(m => { const t = x.res[m]; return `<span class="t2-c ${!t ? "" : t.status === "pass" ? "ok" : "err"}">${!t ? "·" : t.status === "pass" ? "✓" : "✕"}</span>`; }).join("")}</div>`;
        }).join("") : `<p class="muted small">Тесты ещё не гоняли на эталонах этой задачи.</p>`}
        <div class="row mt"><button id="bf-runall" ${isTask ? "" : "disabled"}>Прогнать на обоих эталонах</button><button class="link" id="bf-newtest">+ тест</button></div>
        <div class="insp-code" id="bf-code" hidden></div>`;
      const ra = $("#bf-runall", ib);
      if (ra) ra.onclick = async () => { ra.disabled = true; ra.innerHTML = '<span class="spinner">гоняю</span>'; await runCheck(null); inspect(key); };
      $("#bf-newtest", ib).onclick = async () => {
        const name = prompt("Файл теста", "tests/test_new.py");
        if (!name) return;
        const host = $("#bf-code", ib); host.hidden = false;
        if (!isTask) d.files = { ...d.files, [name]: d.files?.[name] || "def test_example():\n    assert True\n" };
        else if (!files.includes(name)) await writeFile(name, "def test_example():\n    assert True\n");
        await editorIn(host, name, "python");
      };
    } else {
      const paths = isTask ? (await listFiles("data")).map(f => f.path) : Object.keys(d.files || {}).filter(p => p.startsWith("data/"));
      ib.innerHTML = paths.length ? paths.map(p => `<div class="mono small" style="padding:3px 0">${esc(p)}</div>`).join("") : '<p class="muted small">data/ пуста</p>';
    }
  }

  // ---- верхние кнопки ----
  $("#bf-save").onclick = async () => {
    try {
      if (cycles.length) {  // с циклом зависимости не меняем: сохраняем только раскладку
        await api("/api/builder/board", { method: "PUT", json: { task_id: root ? root.id : null, board: boardState() } });
        dirty = false; renderStatus();
        return showMsg("есть цикл — раскладка сохранена как черновик, зависимости задач не изменены");
      }
      const drafts = Object.values(byKey).filter(d => d.kind === "draft").map(d => ({ key: d.key.slice(2), title: d.title, topic_id: d.topic_id ?? ($("#bf-topic").value ? +$("#bf-topic").value : null),
        tags: d.tags?.length ? d.tags : tags, files: d.files || {}, meta: d.meta || {}, main: d.main || "solution.py", implements: d.implements || "" }));
      const r = await api("/api/builder/save", { method: "POST", json: { task_id: root ? root.id : null, drafts, edges: edgeList(), board: boardState() } });
      if (root) await api(`/api/tasks/${root.id}`, { method: "PATCH", json: { title: $("#bf-title").value.trim() || root.title, topic_id: $("#bf-topic").value ? +$("#bf-topic").value : null, tags } }).catch(() => {});
      const fresh = await api("/api/builder/palette");  // черновики стали задачами: обновить карточки
      P.tasks = fresh.tasks;
      fresh.tasks.forEach(t => { cards[`t:${t.id}`] = { ...t, _check: cards[`t:${t.id}`]?._check, _res: cards[`t:${t.id}`]?._res, _fails: cards[`t:${t.id}`]?._fails }; });
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
      renderStatus();
      showMsg(`сохранено: новых задач ${Object.keys(r.created).length}, зависимости обновлены у ${r.changed.length}`, "muted");
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
    const btn = $("#bf-check");
    btn.disabled = true;
    for (const [i, k] of tasks.entries()) {
      const c = cards[k];
      $("#bf-status").textContent = `проверяю ${i + 1}/${tasks.length}: ${c.name}`;
      const { job } = await api(`/api/tasks/${c.id}/check`, { method: "POST" });
      const r = (await followJob(job, () => {})).result.check;
      c._check = r;
      c.tests = { ...c.tests, ...Object.fromEntries(Object.entries(r.modes || {}).map(([m, v]) => [m, [v.passed, v.total]])) };
      c._fails = r.tests.filter(t => ["fail", "error"].includes(t.status)).map(t => { const eg = expectedGot(t.message, t.text); return { name: t.name, mode: t.mode, note: eg ? `ожидалось ${eg.expected}, получено ${eg.got}` : (t.message || "").split("\n")[0].slice(0, 120) }; });
      refreshNode(k);
    }
    btn.disabled = false;
    checkedAt = new Date().toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
    renderStatus();
    if (selected) inspect(selected);
  };
  $("#bf-title").oninput = markDirty;
  $("#bf-topic").onchange = markDirty;
  load(B.board);
  const ro = new ResizeObserver(() => { if (!canvasEl.isConnected) return ro.disconnect(); redraw(); });
  ro.observe(canvasEl);
  current = { leaveGuard: () => !dirty || confirm("На холсте есть несохранённые изменения. Уйти?"), dispose: () => { disposeEd(); document.body.classList.remove("ide-mode"); } };
}

// ---------------- тот же холст — только просмотр ----------------
// без assemble: вкладка «Состав» — стена/блок, где используется задача; сама задача подсвечена, остальное приглушено.
// assemble: экран сборки — у каждой карточки выбор источника (opts.sourceHtml).
async function renderBoardView(el, taskId, opts = {}) {
  await loadDrawflow();
  const P = opts.palette || await api("/api/builder/palette");
  const cards = Object.fromEntries(P.tasks.map(t => [`t:${t.id}`, t]));
  const me = P.tasks.find(t => t.id === +taskId);
  // «Состав»: показываем самое верхнее место, где задача используется (стену), иначе саму задачу
  let rootCard = me;
  if (!opts.assemble) {
    const users = name => P.tasks.filter(t => arr(t.deps).some(d => d.task === name) || (t.deps || []).some(d => d.slot && d.slot === me.implements));
    for (let guard = 0, cur = me; guard < 6; guard++) {
      const up = users(cur.name).sort((a, b) => (b.level === "wall") - (a.level === "wall"))[0];
      if (!up || up.id === cur.id) break;
      rootCard = cur = up;
    }
  }
  el.style.height = opts.height || "560px";
  const { editor, drawMini, fit } = makeCanvas(el, { readonly: true });
  const g = depGraph(rootCard, P);
  let keys = g.keys, edges = g.edges;
  if (opts.assemble) {  // экран сборки: узлы сборки (режим задачи учтён на сервере)
    const nodes = arr(opts.assemble.nodes);
    keys = [`t:${rootCard.id}`];
    edges = [];
    nodes.forEach(n => {
      const key = n.kind === "slot" ? `s:${n.slot}` : `t:${n.task_id}`;
      if (!keys.includes(key)) keys.push(key);
      g.nodes[key] = n.kind === "slot" ? { key, kind: "slot", slot: n.slot, impls: arr(n.impls).map(i => i.name), impl: n.task_name, asmName: n.name }
                                      : { key, kind: "task", task_id: n.task_id, asmName: n.name };
      const parent = n.parent ? nodes.find(x => x.name === n.parent) : null;
      edges.push({ source: key, target: parent ? (parent.kind === "slot" ? `s:${parent.slot}` : `t:${parent.task_id}`) : `t:${rootCard.id}` });
    });
  }
  const pos = autoLayout(keys, edges);
  const ids = {};
  const isWall = rootCard.level === "wall";
  keys.forEach(k => {
    const d = g.nodes[k];
    if (k === `t:${rootCard.id}` && isWall) d.wallOut = (rootCard.main || "pipeline").replace(/\.py$/, "");
    const card = d.kind === "slot" ? slotCard(d, P) : cards[k];
    const n = opts.assemble && d.asmName ? opts.assemble.nodes.find(x => x.name === d.asmName) : null;
    const extra = n ? opts.sourceHtml(d.asmName, n) : "";
    const hl = !opts.assemble && rootCard.id !== me.id ? (k === `t:${me.id}` || (d.kind === "slot" && d.impl === me.name) ? " bf-hl" : " bf-dim") : "";
    ids[k] = editor.addNode(k, d.kind === "slot" ? 0 : 1, 1, pos[k].x, pos[k].y, nodeClass(d, card) + hl, {}, cardHtml(d, card, extra));
    const node = $(`#node-${ids[k]}`, el);
    if (d.kind === "task" && !opts.assemble) { node.ondblclick = () => { location.hash = `#/task/${d.task_id}`; }; node.title = "двойной клик — перейти к задаче"; }
  });
  edges.forEach(e => editor.addConnection(ids[e.source], ids[e.target], "output_1", "input_1"));
  $$(".bf-impl", el).forEach(s => { s.disabled = !opts.assemble; s.onmousedown = e => e.stopPropagation(); });
  if (opts.onImpl) $$(".bf-impl", el).forEach(s => s.onchange = () => opts.onImpl(s.dataset.implFor, s.value));
  if (opts.assemble) $$(".src-pill, .src-menu", el).forEach(s => { s.onmousedown = e => e.stopPropagation(); });
  setTimeout(() => { drawFrame(editor, el, isWall ? { title: rootCard.title, hint: opts.hint || "только просмотр" } : null); fit(); requestAnimationFrame(drawMini); }, 30);
  return { editor, rootCard, me };
}
