// Кирпичики: дерево тем в библиотеке, экран сборки, граф «Состав», мастер «Новая задача»,
// «Вынести в кирпичик» / «Создать слот», сборка в попытке.

const SOURCE_NAME = { self_library: "сам · библиотекой", self_scratch: "сам · с нуля", self: "сам · с нуля", ref: "эталон", last: "моя последняя" };
const SOURCES = ["self_library", "self_scratch", "ref", "last"];
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
        <span class="tcount" title="задач в узле и ниже · пора повторить · запланировано">${t.total}${t.total_due ? ` · <span class="warn">${t.total_due}</span>` : ""}${t.total_planned ? ` · <span class="planned-n">◌${t.total_planned}</span>` : ""}</span>
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
async function viewAssemble(id, mode) {
  const t = normTask(await api(`/api/tasks/${id}`));
  mode = t.modes.includes(mode) ? mode : t.default_mode;  // режим самой составной задачи
  const normOpt = o => ({ ...o, nodes: arr(o?.nodes).map(n => ({ ...n, impls: arr(n.impls), modes: arr(n.modes) })), last: o?.last || {} });
  let opt = normOpt(await api(`/api/tasks/${id}/assembly?mode=${mode}`));
  let asm = Object.fromEntries(opt.nodes.map(n => [n.name, { source: n.source, ...(n.kind === "slot" ? { impl: n.task_name } : {}) }]));
  const lastAsm = opt.last;
  const [P, topics] = await Promise.all([api("/api/builder/palette"), apiList("/api/topics")]);
  const cardBy = Object.fromEntries(P.tasks.map(c => [c.id, c]));
  // источник на сборке (стр. 12, 27): Н — сам · с нуля, Б — сам · библиотекой, Э — эталон, П — моя последняя
  const SRC = { self_scratch: ["Н", "сам · с нуля", "пишешь, как устроено"], self_library: ["Б", "сам · библиотекой", "пишешь, применяя готовое"],
                ref: ["Э", "эталон", "подставится, не в оценке"], last: ["П", "моя последняя", "твоя прошлая версия"] };
  const srcOff = (n, s) => s === "last" ? !n.last : s.startsWith("self_") && !n.modes.includes(s.slice(5));
  async function refresh() {
    opt = normOpt(await api(`/api/tasks/${id}/assembly?mode=${mode}&asm=${encodeURIComponent(JSON.stringify(asm))}`));
    asm = Object.fromEntries(opt.nodes.map(n => [n.name, { source: asm[n.name]?.source || "ref", ...(n.kind === "slot" ? { impl: n.task_name } : {}) }]));
    render();
  }
  function render() {
    const nodes = opt.nodes;
    const self = nodes.filter(n => (asm[n.name]?.source || "ref").startsWith("self_"));
    const due = nodes.filter(n => Object.entries(n.statuses || {}).some(([, s]) => s === "due" || s === "weak"));
    const tests = [...self, { task_id: t.id, self: true }].map(n => { const c = cardBy[n.task_id]; const m = n.self ? mode : asm[n.name].source.slice(5); return c?.tests?.[m]?.[1]; });
    const known = tests.every(x => x != null);
    document.body.classList.add("ide-mode");
    view.innerHTML = `<div class="as-page">
      <div class="ide-top">
        <a href="#/task/${id}" class="icon-btn ide-back" title="назад">←</a>
        <div class="ide-title"><div class="crumbs">${esc(topicPath(topics, t.topic_id) || "Задачи").replaceAll(" / ", '<span class="sep">/</span>')}<span class="sep">/</span>Сборка перед стартом</div>
          <div class="ide-name"><span class="title">${esc(t.title)}</span>${levelTag(t.level)}${modeBadge(mode)}<span class="badge plan">только просмотр</span></div></div>
        <span class="grow"></span>
        ${nodes.length ? `<span class="faint small">быстро:</span><div class="seg" style="margin:0"><button data-all="ref">всё эталоном</button><button data-all="self">всё сам</button>
          ${opt.has_last ? '<button id="as-last">как в прошлый раз</button>' : ""}</div>` : ""}
        <button class="primary" id="as-go">${ICON.play}Начать</button>
      </div>
      <div class="as-cols">
        <div class="as-board" id="as-board">${nodes.length ? "" : emptyState({ icon: "blocks", title: "Собирать нечего", text: "У этой задачи нет зависимостей — можно сразу начинать." })}</div>
        <aside class="as-side">
          <div class="label">Источник для каждой карточки</div>
          ${Object.entries(SRC).map(([k, [, n, d]]) => `<div class="as-leg"><span class="src-pill s-${k}">${n}</span><span class="muted">${d}</span></div>`).join("")}
          <div class="insp-sep"></div>
          <div class="label">Пишешь сам</div>
          <div class="as-self"><div><i class="sq ${catClass(cardBy[t.id]?.category)}"></i><span class="mono">${esc(t.name)}</span><span class="grow"></span>${modeBadge(mode, { short: true })}</div>
            ${self.map(n => `<div><i class="sq ${catClass(cardBy[n.task_id]?.category)}"></i><span class="mono">${esc(n.kind === "slot" ? `${n.task_name} (${n.slot})` : n.name)}</span><span class="grow"></span>${modeBadge(asm[n.name].source.slice(5), { short: true })}</div>`).join("")}</div>
          ${known ? `<div class="as-kv"><span class="muted">тестов в оценке</span><b>${tests.reduce((a, b) => a + b, 0)}</b></div>` : ""}
          ${due.slice(0, 3).map(n => { const m = Object.entries(n.statuses).find(([, s]) => s === "due" || s === "weak")[0];
            return `<div class="as-hint"><b><i class="t-dot" style="background:var(--due);display:inline-block;margin:0 6px 1px 0"></i>${esc(n.name)} · ${MODE_NAME[m]} — пора повторить</b>
              <p class="muted">Выбери на его карточке «сам · ${MODE_NAME[m]}» — повтор засчитается в этой задаче.</p></div>`; }).join("")}
          <span class="grow"></span>
          <button class="primary wide" id="as-go2">Начать</button>
        </aside>
      </div></div>`;
    current = { dispose: () => document.body.classList.remove("ide-mode") };
    if (nodes.length) renderBoardView($("#as-board"), id, { height: "100%", palette: P, assemble: opt, hint: "только просмотр · выбери источник на карточках",
      onImpl: (key, impl) => { const n = nodes.find(x => `s:${x.slot}` === key); if (n) { asm[n.name] = { ...asm[n.name], impl }; refresh(); } },
      sourceHtml: (name, n) => { const s = asm[name]?.source || "ref";
        return `<span class="src-wrap"><button class="src-pill s-${s}" data-src-open="${esc(name)}">${SRC[s][1]} ▾</button>
          <span class="src-menu" data-src-menu="${esc(name)}" hidden>${Object.entries(SRC).map(([k, [l, n2]]) => `<button data-src-set="${esc(name)}" data-v="${k}" ${srcOff(n, k) ? "disabled" : ""}
            title="${srcOff(n, k) ? (k === "last" ? "нет версии, где все тесты прошли" : "у кирпичика нет этого режима") : ""}"><span class="src-l s-${k}">${l}</span>${n2}<span class="faint small">${k === "ref" ? "не в оценке" : k === "last" && n.last ? esc(n.last.from || "") : ""}</span></button>`).join("")}</span></span>`; } })
      .then(() => {
        $$("[data-src-open]").forEach(b => { b.onmousedown = e => e.stopPropagation(); b.onclick = e => { e.stopPropagation(); const m = $(`[data-src-menu="${CSS.escape(b.dataset.srcOpen)}"]`); const was = m.hidden; $$("[data-src-menu]").forEach(x => { x.hidden = true; }); m.hidden = !was; }; });
        $$("[data-src-set]").forEach(b => { b.onmousedown = e => e.stopPropagation(); b.onclick = () => { asm[b.dataset.srcSet] = { ...asm[b.dataset.srcSet], source: b.dataset.v }; refresh(); }; });
        document.addEventListener("click", () => $$("[data-src-menu]").forEach(x => { x.hidden = true; }), { once: true });
      });
    $$("[data-all]").forEach(b => b.onclick = () => {
      const want = b.dataset.all;  // «всё сам»: в режиме задачи, если у кирпичика он есть
      opt.nodes.forEach(n => { asm[n.name] = { ...asm[n.name], source: want === "ref" ? "ref" : n.modes.includes(mode) ? `self_${mode}` : `self_${n.modes[0] || "scratch"}` }; });
      refresh();
    });
    const last = $("#as-last");
    if (last) last.onclick = () => { asm = JSON.parse(JSON.stringify(lastAsm)); refresh(); };
    const go = async () => {
      try { const a = await api(`/api/tasks/${id}/attempts`, { method: "POST", json: { assembly: asm, mode } }); location.hash = `#/attempt/${a.id}`; }
      catch (e) { toast(e.message, true); }
    };
    $("#as-go").onclick = go; $("#as-go2").onclick = go;
  }
  render();
}

// ---------- граф «Состав» — холст конструктора в режиме «только просмотр» ----------
async function renderComposition(box, id) {
  box.innerHTML = '<div class="card comp-card"><div class="comp-head" id="comp-h"></div><div id="compose-board"></div></div>';
  const v = await renderBoardView($("#compose-board", box), id, { height: "560px", hint: "только просмотр" });
  const me = v.me, root = v.rootCard;
  $("#comp-h", box).innerHTML = `<span class="muted">${root.id === me.id ? (arr(me.deps).length ? `Из чего собрана <span class="mono">${esc(me.name)}</span>` : `<span class="mono">${esc(me.name)}</span> ни от чего не зависит и пока нигде не используется`)
    : me.implements ? `<span class="mono">${esc(me.name)}</span> стоит в слоте <span class="mono">${esc(me.implements)}</span> ${root.level === "wall" ? "стены" : "задачи"} «${esc(root.title)}»`
    : `<span class="mono">${esc(me.name)}</span> входит в ${root.level === "wall" ? "стену" : "задачу"} «${esc(root.title)}»`}</span>
    <span class="grow"></span><span class="badge plan">только просмотр</span><a class="btn link" href="#/builder/${root.id}">Открыть в конструкторе</a>`;
}

// ---------- мастер «Новая задача» ----------
const WIZ_REF = "def solve(xs):\n    return sorted(xs)\n";
const WIZ_TEST = "from solution import solve\n\n\ndef test_example():\n    assert solve([3, 1, 2]) == [1, 2, 3]\n";
async function wizardDialog(preset = {}) {
  const [topics, tasks, slots] = await Promise.all([apiList("/api/topics"), apiList("/api/tasks"), apiList("/api/slots")]);
  const st = { step: 1, title: preset.title || "", topic_id: preset.topic_id ?? null, tags: "", kind: "algo", type: "plain", implements: "", newSlot: "",
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
      <span class="badge ${b.source.startsWith("self") ? "warn" : ""}">${SOURCE_NAME[b.source] || b.source}</span></div>`).join("")}
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
