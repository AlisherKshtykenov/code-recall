// Кирпичики: дерево тем в библиотеке, экран сборки, граф «Состав», мастер «Новая задача»,
// «Вынести в кирпичик» / «Создать слот», сборка в попытке.

const SOURCE_NAME = { self: "пишу сам", ref: "эталон", last: "моя последняя" };
const TYPE_BADGE = { composite: ["", "составная"], slot: ["", "кирпичик"], plain: null };
const NODE_STATUS = { solved: ["ok", "решено"], due: ["warn", "пора повторить"], new: ["muted", "новая"],
                      broken: ["err", "сломано зависимостью"], failed: ["err", "упал в задаче"] };
// Ответы API без нужного списка (старый сервер, NULL в базе) не роняют экран: вместо undefined — []
const arr = x => Array.isArray(x) ? x : [];
const apiList = path => api(path).then(arr).catch(() => []);
function normTask(t) {
  t.tags = arr(t.tags); t.deps = arr(t.deps);
  t.type ||= t.deps.length ? "composite" : t.implements ? "slot" : "plain";
  t.implements ||= ""; t.broken ||= "";
  return t;
}

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* приватное окно */ } },
};

// ---------- дерево тем ----------
function topicTree(topics) {
  topics = arr(topics);
  const kids = {};
  topics.forEach(t => (kids[t.parent_id ?? "root"] ||= []).push(t));
  Object.values(kids).forEach(l => l.sort((a, b) => a.position - b.position || a.name.localeCompare(b.name)));
  return kids;
}
function subtreeIds(kids, id) {
  const out = [id];
  (kids[id] || []).forEach(k => out.push(...subtreeIds(kids, k.id)));
  return out;
}
function topicPath(topics, id) {
  const by = Object.fromEntries(arr(topics).map(t => [t.id, t]));
  const parts = [];
  for (let t = by[id]; t; t = by[t.parent_id]) parts.unshift(t.name);
  return parts.join(" / ");
}
function topicOptions(topics, sel) {
  const kids = topicTree(topics), out = [];
  const walk = (pid, d) => (kids[pid] || []).forEach(t => { out.push(`<option value="${t.id}" ${t.id === sel ? "selected" : ""}>${"  ".repeat(d)}${d ? "└ " : ""}${esc(t.name)}</option>`); walk(t.id, d + 1); });
  walk("root", 0);
  return out.join("");
}

// Левая панель библиотеки: дерево (сворачивается), перетаскивание узлов и задач, ＋ / ✎ / ✕
function renderTopicTree(box, topics, state, onChange) {
  topics = arr(topics);
  const kids = topicTree(topics);
  const collapsed = new Set(store.get("topics.collapsed", []));
  const all = topics.filter(t => t.parent_id == null).reduce((s, t) => [s[0] + t.total, s[1] + t.total_due], [0, 0]);
  const row = (t, d) => {
    const has = (kids[t.id] || []).length, open = !collapsed.has(t.id);
    return `<div class="tnode ${state.topic === t.id ? "sel" : ""}" data-topic="${t.id}" draggable="true" style="padding-left:${8 + d * 14}px">
        <span class="caret" data-caret="${t.id}">${has ? (open ? "▾" : "▸") : ""}</span><span class="tname grow">${esc(t.name)}</span>
        <span class="tcount" title="задач в узле и ниже · пора повторить">${t.total}${t.total_due ? ` · <span class="warn">${t.total_due}</span>` : ""}</span>
        <span class="tact"><button class="icon-btn" data-add="${t.id}" title="подузел">＋</button><button class="icon-btn" data-ren="${t.id}" title="переименовать">✎</button><button class="icon-btn" data-del="${t.id}" title="удалить узел (задачи перейдут выше)">✕</button></span></div>
      ${has && open ? (kids[t.id] || []).map(k => row(k, d + 1)).join("") : ""}`;
  };
  box.innerHTML = `<div class="row" style="margin-bottom:6px"><b class="grow">Темы</b><button class="icon-btn" data-add="" title="новый узел в корне">＋</button></div>
    <div class="tnode ${state.topic == null ? "sel" : ""}" data-topic="" style="padding-left:8px"><span class="caret"></span><span class="tname grow">Все задачи</span>
      <span class="tcount">${all[0]}${all[1] ? ` · <span class="warn">${all[1]}</span>` : ""}</span></div>
    ${(kids.root || []).map(t => row(t, 0)).join("") || '<p class="muted small" style="padding:4px 8px">Тем пока нет — ＋ создайте первую.</p>'}
    ${topics.length ? '<p class="muted small mt">Перетащите задачу или узел на узел, чтобы перенести.</p>' : ""}`;
  box.onclick = async e => {
    const b = e.target.closest("button"), caret = e.target.closest("[data-caret]");
    if (caret && caret.textContent) {
      const id = +caret.dataset.caret;
      collapsed.has(id) ? collapsed.delete(id) : collapsed.add(id);
      store.set("topics.collapsed", [...collapsed]);
      return renderTopicTree(box, topics, state, onChange);
    }
    if (b?.dataset.add !== undefined) {
      const name = prompt("Название узла");
      if (!name) return;
      await api("/api/topics", { method: "POST", json: { name, parent_id: b.dataset.add ? +b.dataset.add : null } });
      return onChange();
    }
    if (b?.dataset.ren) {
      const t = topics.find(x => x.id === +b.dataset.ren), name = prompt("Новое название", t.name);
      if (!name) return;
      await api(`/api/topics/${t.id}`, { method: "PATCH", json: { name } });
      return onChange();
    }
    if (b?.dataset.del) {
      const t = topics.find(x => x.id === +b.dataset.del);
      if (!confirm(`Удалить узел «${t.name}»? Задачи и подузлы перейдут в родительский узел.`)) return;
      await api(`/api/topics/${t.id}`, { method: "DELETE" });
      if (state.topic === t.id) state.topic = null;
      return onChange();
    }
    const n = e.target.closest("[data-topic]");
    if (n) { state.topic = n.dataset.topic ? +n.dataset.topic : null; store.set("lib.topic", state.topic); onChange(false); }
  };
  // перетаскивание: узел на узел — перенос узла; задача (строка таблицы) на узел — перенос задачи
  $$("[data-topic]", box).forEach(el => {
    el.ondragstart = e => { e.dataTransfer.setData("text/topic", el.dataset.topic); };
    el.ondragover = e => { e.preventDefault(); el.classList.add("over"); };
    el.ondragleave = () => el.classList.remove("over");
    el.ondrop = async e => {
      e.preventDefault(); el.classList.remove("over");
      const target = el.dataset.topic ? +el.dataset.topic : null;
      const task = e.dataTransfer.getData("text/task"), node = e.dataTransfer.getData("text/topic");
      try {
        if (task) { if (target == null) return; await api(`/api/tasks/${task}`, { method: "PATCH", json: { topic_id: target } }); }
        else if (node && +node !== target) await api(`/api/topics/${node}`, { method: "PATCH", json: { parent_id: target, move: true } });
        onChange();
      } catch (err) { toast(err.message, true); }
    };
  });
  return kids;
}

// ---------- экран сборки ----------
async function viewAssemble(id) {
  const t = normTask(await api(`/api/tasks/${id}`));
  const normOpt = o => ({ ...o, nodes: arr(o?.nodes).map(n => ({ ...n, impls: arr(n.impls) })), last: o?.last || {} });
  let opt = normOpt(await api(`/api/tasks/${id}/assembly`));
  let asm = Object.fromEntries(opt.nodes.map(n => [n.name, { source: n.source, ...(n.kind === "slot" ? { impl: n.task_name } : {}) }]));
  const lastAsm = opt.last;
  async function refresh() {
    opt = normOpt(await api(`/api/tasks/${id}/assembly?asm=${encodeURIComponent(JSON.stringify(asm))}`));
    asm = Object.fromEntries(opt.nodes.map(n => [n.name, { source: asm[n.name]?.source || "ref", ...(n.kind === "slot" ? { impl: n.task_name } : {}) }]));
    render();
  }
  function render() {
    const nodes = opt.nodes;
    view.innerHTML = `<div class="row" style="margin-bottom:6px"><a href="#/task/${id}" class="muted">← ${esc(t.title)}</a></div>
      <div class="row" style="margin-bottom:12px"><h1 style="margin:0">Сборка перед стартом</h1><span class="grow"></span>
        <button class="ghost" data-all="ref">всё эталоном</button><button class="ghost" data-all="self">всё сам</button>
        ${opt.has_last ? '<button class="ghost" id="as-last">как в прошлый раз</button>' : ""}
        <button class="primary" id="as-go">Начать</button></div>
      <p class="muted small">Для каждой зависимости: <b>пишу сам</b> — файл <span class="mono">bricks/&lt;имя&gt;.py</span> в попытке (его собственные тесты гоняются первыми);
        <b>эталон</b> — подключается скрыто, только для импорта; <b>моя последняя</b> — ваш код из попытки, где все его тесты прошли. Выбор запоминается.</p>
      ${nodes.length ? "" : '<div class="card empty">У этой задачи нет зависимостей — собирать нечего, можно сразу начинать.</div>'}
      <div class="card" ${nodes.length ? "" : "hidden"}><table><thead><tr><th>Импорт</th><th>Кирпичик</th><th>Статус</th><th>Источник</th></tr></thead><tbody>
      ${nodes.map(n => {
        const st = NODE_STATUS[n.status] || NODE_STATUS.new, src = asm[n.name]?.source || "ref";
        return `<tr><td style="padding-left:${10 + n.depth * 18}px" class="mono small">${n.depth ? "└ " : ""}${n.kind === "slot" ? `slots.${esc(n.slot)}` : `bricks.${esc(n.name)}`}</td>
          <td>${n.kind === "slot" ? `<span class="muted small">слот ${esc(n.slot)} →</span> <select data-impl="${esc(n.name)}">${n.impls.map(i => `<option value="${esc(i.name)}" ${i.name === n.task_name ? "selected" : ""}>${esc(i.title)}</option>`).join("")}</select>`
            : `<a href="#/task/${n.task_id}">${esc(n.title)}</a>`}</td>
          <td><span class="${st[0]} small">${st[1]}</span></td>
          <td><div class="seg" style="margin:0">${["self", "ref", "last"].map(s => `<button data-src="${esc(n.name)}" data-v="${s}" class="${src === s ? "sel" : ""}"
              ${s === "last" && !n.last ? 'disabled title="нет версии, где все тесты прошли"' : s === "last" ? `title="${esc(n.last.from)}"` : ""}>${SOURCE_NAME[s]}</button>`).join("")}</div></td></tr>`;
      }).join("")}</tbody></table>
      <p class="muted small mt">Импорт в коде задачи: ${nodes.filter(n => !n.depth).map(n => `<span class="mono">${n.kind === "slot" ? `from slots.${esc(n.slot)} import ${esc(n.symbol)}` : `from bricks.${esc(n.name)} import …`}</span>`).join(" · ")}</p></div>`;
    $$("[data-src]").forEach(b => b.onclick = () => { asm[b.dataset.src] = { ...asm[b.dataset.src], source: b.dataset.v }; render(); });
    $$("[data-impl]").forEach(s => s.onchange = () => { asm[s.dataset.impl] = { ...asm[s.dataset.impl], impl: s.value }; refresh(); });
    $$("[data-all]").forEach(b => b.onclick = () => { Object.values(asm).forEach(x => { x.source = b.dataset.all; }); render(); });
    const last = $("#as-last");
    if (last) last.onclick = () => { asm = JSON.parse(JSON.stringify(lastAsm)); refresh(); };
    $("#as-go").onclick = async () => {
      try { const a = await api(`/api/tasks/${id}/attempts`, { method: "POST", json: { assembly: asm } }); location.hash = `#/attempt/${a.id}`; }
      catch (e) { toast(e.message, true); }
    };
  }
  render();
}

// ---------- граф «Состав» ----------
async function renderComposition(box, id) {
  const g = await api(`/api/tasks/${id}/graph`);
  g.up = arr(g.up); g.down = arr(g.down);
  const card = (n, cls = "") => {
    const st = NODE_STATUS[n.status] || NODE_STATUS.new;
    return `<a class="gnode ${cls}" href="#/task/${n.task_id ?? n.id}" data-g="${n.key}"><b>${esc(n.title)}</b>
      <span class="small ${st[0]}">${st[1]}</span>${n.kind === "slot" ? `<span class="muted small">слот ${esc(n.slot)}</span>` : n.name ? `<span class="muted small mono">bricks.${esc(n.name)}</span>` : ""}</a>`;
  };
  const levels = {};
  g.up.forEach(n => { n.key = `u${n.task_id}`; (levels[-1 - n.depth] ||= []).push(n); });
  levels[0] = [{ ...g, key: "me", task_id: g.id }];
  g.down.forEach(n => { n.key = `d${n.name}`; (levels[1 + n.depth] ||= []).push(n); });
  const keys = Object.keys(levels).map(Number).sort((a, b) => a - b);
  box.innerHTML = `<div class="card"><p class="muted small">Вверху — где используется эта задача, внизу — из чего она собрана (эталонная сборка). Клик — перейти к задаче.</p>
    ${g.error ? `<p class="err">${esc(g.error)}</p>` : ""}${!g.up.length && !g.down.length ? '<p class="muted">Задача ни от чего не зависит и нигде не используется.</p>' : ""}
    <div class="graph" id="graph"><svg class="glines"></svg>${keys.map(k => `<div class="glevel">${levels[k].map(n => card(n, k === 0 ? "me" : "")).join("")}</div>`).join("")}</div></div>`;
  const svg = $(".glines", box), wrap = $("#graph", box);
  const draw = () => {
    const r0 = wrap.getBoundingClientRect(), at = k => { const el = $(`[data-g="${k}"]`, wrap); if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.left - r0.left + r.width / 2, top: r.top - r0.top, bottom: r.bottom - r0.top }; };
    const edges = [...g.up.map(n => [`u${n.task_id}`, n.child === g.id ? "me" : `u${n.child}`]),
                   ...g.down.map(n => [n.parent ? `d${n.parent}` : "me", `d${n.name}`])];
    svg.setAttribute("width", wrap.scrollWidth); svg.setAttribute("height", wrap.scrollHeight);
    svg.innerHTML = edges.map(([a, b]) => { const p = at(a), q = at(b); if (!p || !q) return "";
      const y1 = p.bottom, y2 = q.top, m = (y1 + y2) / 2;
      return `<path d="M${p.x},${y1} C${p.x},${m} ${q.x},${m} ${q.x},${y2}" />`; }).join("");
  };
  requestAnimationFrame(draw);
  // перерисовка при любом изменении размера; наблюдатель отключается, когда граф убрали со страницы
  const ro = new ResizeObserver(() => { if (!wrap.isConnected) return ro.disconnect(); draw(); });
  ro.observe(wrap);
}

// ---------- мастер «Новая задача» ----------
const WIZ_REF = "def solve(xs):\n    return sorted(xs)\n";
const WIZ_TEST = "from solution import solve\n\n\ndef test_example():\n    assert solve([3, 1, 2]) == [1, 2, 3]\n";
async function wizardDialog(preset = {}) {
  const [topics, tasks, slots] = await Promise.all([apiList("/api/topics"), apiList("/api/tasks"), apiList("/api/slots")]);
  const st = { step: 1, title: "", topic_id: preset.topic_id ?? null, tags: "", kind: "algo", type: "plain", implements: "", newSlot: "",
               files: { "reference/solution.py": WIZ_REF, "tests/test_solution.py": WIZ_TEST }, deps: [], cur: "reference/solution.py" };
  const back = document.createElement("div");
  back.className = "modal-back";
  document.body.appendChild(back);
  const close = () => back.remove();
  const STEPS = ["Название", "Тип", "Файлы", "Зависимости", "Проверка эталона"];
  function render() {
    const steps = STEPS.map((n, i) => `<span class="st ${i + 1 === st.step ? "cur" : i + 1 < st.step ? "done" : ""}">${i + 1 < st.step ? "✓" : i + 1} ${n}</span>`).join('<span class="muted">→</span>');
    let body = "";
    if (st.step === 1) body = `<div class="row"><label style="width:90px">Название</label><input id="w-title" class="grow" value="${esc(st.title)}" placeholder="например, MSE"></div>
      <div class="row mt"><label style="width:90px">Узел</label><select id="w-topic" class="grow"><option value="">— выберите —</option>${topicOptions(topics, st.topic_id)}</select></div>
      <div class="row mt"><label style="width:90px">Теги</label><input id="w-tags" class="grow" value="${esc(st.tags)}" placeholder="через запятую: numpy, кирпичик"></div>
      <div class="row mt"><label style="width:90px">Вид</label><select id="w-kind"><option value="algo" ${st.kind === "algo" ? "selected" : ""}>Алгоритм</option><option value="ml" ${st.kind === "ml" ? "selected" : ""}>ML</option></select></div>`;
    else if (st.step === 2) body = `${[["plain", "Обычная", "эталон и тесты"], ["slot", "Реализует слот", "проходит контрактные тесты слота + свои"], ["composite", "Составная", "собрана из других задач и слотов"]]
        .map(([k, n, d]) => `<label class="opt ${st.type === k ? "sel" : ""}"><input type="radio" name="w-type" value="${k}" ${st.type === k ? "checked" : ""}> <b>${n}</b> <span class="muted small">— ${d}</span></label>`).join("")}
      ${st.type === "slot" ? `<div class="row mt"><label>Слот</label><select id="w-slot"><option value="">— новый —</option>${slots.map(s => `<option value="${esc(s.name)}" ${s.name === st.implements ? "selected" : ""}>${esc(s.name)} · ${esc(s.signature || s.title)}</option>`).join("")}</select>
        <input id="w-newslot" placeholder="имя нового слота" value="${esc(st.newSlot)}" ${st.implements ? "hidden" : ""}></div>
        <p class="muted small">Код должен определять ${st.implements ? `<span class="mono">${esc(slots.find(s => s.name === st.implements)?.symbol || st.implements)}</span>` : "функцию с именем слота"}. Контрактные тесты нового слота можно добавить потом.</p>` : ""}`;
    else if (st.step === 3) body = `<div class="row" style="flex-wrap:wrap">${Object.keys(st.files).map(f => `<button class="small ${f === st.cur ? "sel" : "ghost"}" data-f="${esc(f)}">${esc(f)}</button>`).join("")}
        <button class="small ghost" id="w-addf">＋ файл</button>${Object.keys(st.files).length > 1 ? '<button class="small ghost" id="w-delf">✕ этот</button>' : ""}</div>
      <textarea id="w-code" class="mono" spellcheck="false" style="width:100%;height:300px;margin-top:8px;font-size:13px">${esc(st.files[st.cur] || "")}</textarea>
      <p class="muted small">reference/ — эталон, tests/test_*.py — тесты (импорт по имени файла), starter/ — заготовки, description.md — описание.</p>`;
    else if (st.step === 4) body = st.type !== "composite" ? '<p class="muted">У этой задачи нет зависимостей — шаг пропускается. Нужны кирпичики — вернитесь и выберите тип «Составная».</p>'
      : `${st.deps.map((d, i) => `<div class="row" style="margin-bottom:6px"><input data-dn="${i}" value="${esc(d.name)}" placeholder="имя для импорта" style="width:140px">
          <select data-dt="${i}"><optgroup label="Задачи">${tasks.map(x => `<option value="task:${esc(x.name)}" ${d.task === x.name ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</optgroup>
            <optgroup label="Слоты">${slots.map(s => `<option value="slot:${esc(s.name)}" ${d.slot === s.name ? "selected" : ""}>слот ${esc(s.name)}</option>`).join("")}</optgroup></select>
          <span class="mono small muted grow">${d.slot ? `from slots.${esc(d.slot)} import ${esc(slots.find(s => s.name === d.slot)?.symbol || d.slot)}` : `from bricks.${esc(d.name || "?")} import …`}</span>
          <button class="icon-btn" data-dx="${i}">✕</button></div>`).join("")}
        <button class="small" id="w-adddep">＋ зависимость</button><p class="muted small">Циклы запрещены — сервер проверит при создании.</p>`;
    else body = `<div id="w-check"><div class="muted spinner">создаю задачу и гоняю тесты на эталоне</div></div>`;
    back.innerHTML = `<div class="modal" style="width:min(820px,96vw)"><div class="row"><h2 style="margin:0">Новая задача</h2><span class="grow"></span><button class="icon-btn" data-x>✕</button></div>
      <div class="stepper" style="margin:10px 0">${steps}</div>${body}
      <div class="row mt"><span class="err small grow" id="w-err"></span>${st.step > 1 && st.step < 5 ? '<button id="w-back">Назад</button>' : ""}
        ${st.step < 4 ? '<button class="primary" id="w-next">Далее</button>' : st.step === 4 ? '<button class="primary" id="w-create">Создать и проверить эталон</button>' : ""}</div></div>`;
    $("[data-x]", back).onclick = close;
    const nb = $("#w-back", back);
    if (nb) nb.onclick = () => { save(); st.step--; render(); };
    const nx = $("#w-next", back);
    if (nx) nx.onclick = () => { save(); const err = validate(); if (err) { $("#w-err", back).textContent = err; return; } st.step++; render(); };
    const cr = $("#w-create", back);
    if (cr) cr.onclick = () => { save(); create(); };
    $$('[name="w-type"]', back).forEach(r => r.onchange = () => { st.type = r.value; render(); });
    const sl = $("#w-slot", back);
    if (sl) sl.onchange = () => { st.implements = sl.value; render(); };
    $$("[data-f]", back).forEach(b => b.onclick = () => { save(); st.cur = b.dataset.f; render(); });
    const af = $("#w-addf", back);
    if (af) af.onclick = () => { save(); const f = prompt("Путь файла (reference/model.py, tests/test_model.py, starter/model.py, description.md)"); if (!f) return; st.files[f] ??= ""; st.cur = f; render(); };
    const df = $("#w-delf", back);
    if (df) df.onclick = () => { delete st.files[st.cur]; st.cur = Object.keys(st.files)[0]; render(); };
    const ad = $("#w-adddep", back);
    if (ad) ad.onclick = () => { save(); const x = tasks[0]; st.deps.push(x ? { name: x.name.toLowerCase(), task: x.name } : { name: "", slot: slots[0]?.name }); render(); };
    $$("[data-dx]", back).forEach(b => b.onclick = () => { save(); st.deps.splice(+b.dataset.dx, 1); render(); });
    $$("[data-dt]", back).forEach(s => s.onchange = () => { save(); render(); });
  }
  function save() {
    const v = sel => $(sel, back)?.value;
    if (st.step === 1) { st.title = v("#w-title").trim(); st.topic_id = v("#w-topic") ? +v("#w-topic") : null; st.tags = v("#w-tags"); st.kind = v("#w-kind"); }
    if (st.step === 2 && $("#w-newslot", back)) st.newSlot = v("#w-newslot").trim();
    if (st.step === 3 && $("#w-code", back)) st.files[st.cur] = v("#w-code");
    if (st.step === 4) st.deps = st.deps.map((d, i) => {
      const [kind, name] = (v(`[data-dt="${i}"]`) || "").split(":");
      return { name: (v(`[data-dn="${i}"]`) || name || "").trim(), ...(kind === "slot" ? { slot: name } : { task: name }) };
    });
  }
  function validate() {
    if (st.step === 1 && !st.title) return "нужно название";
    if (st.step === 2 && st.type === "slot" && !st.implements && !st.newSlot) return "выберите слот или задайте имя нового";
    if (st.step === 3 && !Object.keys(st.files).some(f => f.startsWith("reference/") && f.endsWith(".py"))) return "нужен хотя бы один reference/*.py";
    return "";
  }
  async function create() {
    if (st.type === "composite" && !st.deps.length) { $("#w-err", back).textContent = "добавьте хотя бы одну зависимость"; return; }
    let impl = st.implements;
    try {
      if (st.type === "slot" && !impl) impl = (await api("/api/slots", { method: "POST", json: { name: st.newSlot } })).name;
      const r = await api("/api/tasks/wizard", { method: "POST", json: {
        title: st.title, topic_id: st.topic_id, tags: st.tags.split(",").map(x => x.trim()).filter(Boolean), kind: st.kind, type: st.type,
        implements: impl, files: st.files, deps: st.type === "composite" ? st.deps : [] } });
      st.step = 5; render();
      const { job } = await api(`/api/tasks/${r.id}/check`, { method: "POST" });
      const box = $("#w-check", back);
      const res = await followJob(job, () => {});
      const c = res.result?.check;
      box.innerHTML = `${testsHtml(c)}<div class="row mt"><span class="grow"></span><a class="btn" href="#/task/${r.id}">К задаче</a><a class="btn primary" href="#/edit/${r.id}">Открыть в редакторе</a></div>`;
      $$("a", box).forEach(a => a.addEventListener("click", close));
    } catch (e) { st.step = Math.min(st.step, 4); render(); $("#w-err", back).textContent = e.message; }
  }
  render();
}

// ---------- «Вынести в кирпичик» / «Создать слот» (в редакторе задачи) ----------
function symbolAtCursor(ide) {
  const ed = ide.editor, model = ed?.getModel();
  if (!model) return null;
  const sel = ed.getSelection(), lines = model.getLinesContent();
  const re = /^(?:async\s+)?(?:def|class)\s+(\w+)/;
  const picked = model.getValueInRange(sel).split("\n").find(l => re.test(l.trim()));
  if (picked) return picked.trim().match(re)[1];
  for (let i = sel.startLineNumber - 1; i >= 0; i--) { const m = lines[i].match(re); if (m) return m[1]; }  // ближайший def/class выше курсора (верхнего уровня)
  return null;
}
async function extractBrick(taskId, ide, asSlot) {
  const path = ide.current;
  if (!path || !path.startsWith("reference/") || !path.endsWith(".py")) return toast("откройте файл эталона (reference/*.py) и поставьте курсор в функцию или класс", true);
  const sym = symbolAtCursor(ide);
  if (!sym) return toast("не нашёл def/class: выделите функцию или класс", true);
  const title = prompt(asSlot ? `Слот из функции ${sym}. Название реализации:` : `Вынести ${sym} в новую задачу-кирпичик. Название:`, sym);
  if (!title) return;
  const dep = prompt(asSlot ? "Имя слота (для from slots.<имя> import …)" : "Имя для импорта (from bricks.<имя> import …)", sym.toLowerCase());
  if (!dep) return;
  await ide.saveAll();
  try {
    const r = await api(`/api/tasks/${taskId}/extract`, { method: "POST", json: { file: path, symbol: sym, title, dep_name: dep, as_slot: asSlot } });
    toast(`${asSlot ? "слот создан" : "кирпичик создан"}: ${r.import}`);
    if (ide.models[path]) ide.models[path].setValue((await api(`/api/tasks/${taskId}/file?path=${encodeURIComponent(path)}`)).content);
    if (confirm(`Готово: в коде теперь «${r.import}». Открыть новую задачу-кирпичик?`)) location.hash = `#/edit/${r.brick_id}`;
  } catch (e) { toast(e.message, true); }
}

// ---------- сборка в попытке (вкладка слева) ----------
function renderAssemblyTab(el, a) {
  a.bricks = arr(a.bricks);
  const slots = a.bricks.filter(b => b.kind === "slot");
  el.innerHTML = `<p class="muted small">Кирпичики этой попытки. «Пишу сам» — файлы <span class="mono">bricks/…</span> в редакторе; при «Проверить» сначала гоняются их собственные тесты.</p>
    ${a.bricks.map(b => b.error ? `<p class="err small">${esc(b.error)}</p>` : `<div class="row small" style="padding:4px 0 4px ${b.depth * 14}px;border-bottom:1px solid var(--line)">
      <span class="mono">${b.kind === "slot" ? `slots.${esc(b.slot)}` : `bricks.${esc(b.name)}`}</span><span class="grow"><a href="#/task/${b.task_id}">${esc(b.title)}</a></span>
      <span class="badge ${b.source === "self" ? "warn" : ""}">${SOURCE_NAME[b.source]}</span></div>`).join("")}
    ${slots.length && a.status === "active" ? '<button class="mt" id="all-impl">Проверить со всеми реализациями слота</button><div id="impl-out" class="mt"></div>' : ""}`;
  const b = $("#all-impl", el);
  if (b) b.onclick = async () => {
    const out = $("#impl-out", el);
    out.innerHTML = '<div class="muted spinner small">гоняю тесты с каждой реализацией</div>';
    try {
      const { job } = await api(`/api/attempts/${a.id}/check_slots`, { method: "POST" });
      const r = (await followJob(job, () => {})).result;
      out.innerHTML = `<table><thead><tr><th>Слот</th><th>Реализация</th><th>Тесты</th></tr></thead><tbody>${arr(r?.slots).map(x => `<tr><td class="mono">${esc(x.slot)}</td>
        <td>${esc(x.title)}${x.current ? ' <span class="muted small">(в сборке)</span>' : ""}</td>
        <td>${x.fatal ? `<span class="err small">${esc(x.fatal)}</span>` : `<b class="${x.passed === x.total && x.total ? "ok" : "err"}">${x.passed}/${x.total}</b>`}</td></tr>`).join("")}</tbody></table>`;
    } catch (e) { out.innerHTML = `<p class="err small">${esc(e.message)}</p>`; }
  };
}
