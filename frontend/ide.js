// Мини-IDE: описание | редактор (Monaco) + консоль | файлы. Используется для попытки и для редактора задачи.
/* global monaco */

const LAYOUT_KEY = "ide-layout-v1";
function loadLayout() {
  try { return { left: 360, right: 260, bottom: 240, lc: false, rc: false, bc: false, ...JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") }; }
  catch { return { left: 360, right: 260, bottom: 240, lc: false, rc: false, bc: false }; }
}
function saveLayout(l) { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(l)); } catch { /* приватный режим */ } }

const FILE_ICON = { dir: "▸", python: "Py", table: "▦", json: "{}", markdown: "M↓", image: "▣", video: "▶", audio: "♪", text: "≡", file: "·", broken: "⚠" };
const EDITABLE = /\.(py|md|txt|toml|ya?ml|cfg|ini|sh|sql|html|xml|gitignore)$/i;
const LANG = { py: "python", md: "markdown", json: "json", yaml: "yaml", yml: "yaml", html: "html", xml: "xml", sh: "shell", sql: "sql" };

/*
cfg = {
  title, base,                       // base: "/api/attempts/3" или "/api/tasks/2" — файловое API
  readonly,                          // попытка сдана: только чтение
  open: [пути],                      // открыть при старте
  roles: {файл: write|given},        // подписи у вкладок
  leftTabs: [{id, label, render(el, ide)}], leftTab,
  buttons(el, ide),                  // кнопки справа в верхней панели (таймер, «Сдать» …)
  run(path) -> jobId, exec(code) -> jobId, stop(), check() -> jobId,   // действия (необязательные)
  runnable(path) -> bool,
  diffs: {файл: текст эталона}       // режим просмотра: вкладка открывается как diff
  bindData(), dataLink
}
*/
async function openIDE(root, cfg) {
  document.body.classList.add("ide-mode");
  const L = loadLayout();
  root.innerHTML = `
    <div class="ide">
      <div class="ide-top">
        <a href="${cfg.back || "#/tasks"}" class="icon-btn" title="назад">←</a>
        <span class="title">${esc(cfg.title)}</span>
        <span class="grow"></span>
        ${cfg.run && !cfg.readonly ? `<select id="ide-main" class="small" title="что запускает «Запустить»"></select>
          <button id="ide-run" class="success" title="Ctrl/Cmd+Enter">▶ Запустить</button>
          <button id="ide-stop" class="ghost" title="остановить запуск или тесты">■ Стоп</button>` : ""}
        ${cfg.check && !cfg.readonly ? `<button id="ide-check" class="ghost" title="прогнать тесты, попытка не засчитывается">✓ Проверить</button>` : ""}
        <span id="ide-buttons" class="row"></span>
      </div>
      <div class="ide-body" id="ide-body">
        <section class="pane" id="p-left">
          <div class="pane-head"><div class="tabs" id="left-tabs"></div><button class="icon-btn collapse" data-collapse="lc" title="свернуть">⟨</button></div>
          <div class="pane-body" id="left-body" style="padding:14px 16px"></div>
        </section>
        <div class="gutter v" data-g="left"></div>
        <div class="center-col" id="center">
          <section class="pane">
            <div class="pane-head" style="padding:0">
              <div class="filetabs" id="filetabs"></div>
            </div>
            <div class="editor-host" id="editor-host"><div class="monaco" id="monaco"></div><div class="viewer" id="viewer" hidden></div></div>
          </section>
          <div class="gutter h" data-g="bottom"></div>
          <section class="pane console-pane" id="p-bottom">
            <div class="pane-head"><div class="tabs" id="con-tabs">
                <button data-ct="out" class="active">Вывод</button><button data-ct="tests">Тесты</button><button data-ct="repl">Консоль</button></div>
              <span class="grow hide-collapsed"></span>
              <button class="icon-btn hide-collapsed" id="con-clear" title="очистить">⌫</button>
              <button class="icon-btn collapse" data-collapse="bc" title="свернуть" style="margin-left:0">⌄</button></div>
            <div class="pane-body console-scroll" id="con-body">
              <div class="console-body" data-cv="out"><div class="muted">Здесь появится вывод «Запустить»: print, таблицы show(df) и графики plt.show().</div></div>
              <div class="console-body" data-cv="tests" hidden>${testsHtml(null)}</div>
              <div class="console-body" data-cv="repl" hidden><div class="muted">Python-консоль в папке ${cfg.base.includes("attempts") ? "попытки" : "задачи"}: после «Запустить» переменные скрипта доступны здесь (например <code>df.head()</code>).
                Enter — выполнить, Shift+Enter — новая строка, ↑/↓ — история.</div><div id="repl-log"></div></div>
            </div>
            ${cfg.exec && !cfg.readonly ? `<div class="repl-input" id="repl-in" hidden><span class="prompt">&gt;&gt;&gt;</span><textarea rows="1" spellcheck="false" placeholder="df.head()"></textarea></div>` : ""}
          </section>
        </div>
        <div class="gutter v" data-g="right"></div>
        <section class="pane" id="p-right">
          <div class="pane-head"><span class="label hide-collapsed" style="margin:0 6px">Файлы</span><span class="grow hide-collapsed"></span>
            <button class="icon-btn collapse" data-collapse="rc" title="свернуть">⟩</button></div>
          <div class="pane-body" style="display:flex;flex-direction:column">
            <div class="tree-tools">
              ${cfg.readonly ? "" : `<button class="icon-btn" data-tt="file" title="новый файл">＋</button><button class="icon-btn" data-tt="dir" title="новая папка">▸＋</button>
                <button class="icon-btn" data-tt="upload" title="загрузить файлы (или перетащите на дерево)">⇪</button>`}
              ${cfg.bindData && !cfg.readonly ? `<button class="icon-btn" data-tt="bind" title="подключить папку с датасетом как data/">⛓</button>` : ""}
              <span class="grow"></span><button class="icon-btn" data-tt="refresh" title="обновить">↻</button>
              <input type="file" id="tree-up" multiple hidden></div>
            <div class="tree" id="tree" style="flex:1;overflow:auto"></div>
            <div class="small muted" id="data-note" style="padding:6px 10px;border-top:1px solid var(--line)"></div>
          </div>
        </section>
      </div>
    </div>`;

  const ide = { cfg, tabs: [], current: null, models: {}, savedVersion: {}, alive: true, lastCheck: null, outRuns: 0 };
  const body = $("#ide-body", root), center = $("#center", root);

  // ---------- раскладка: перетаскивание границ и сворачивание ----------
  function applyLayout() {
    $("#p-left", root).classList.toggle("collapsed", L.lc);
    $("#p-right", root).classList.toggle("collapsed", L.rc);
    $("#p-bottom", root).classList.toggle("collapsed", L.bc);
    const narrow = window.innerWidth < 900;  // телефон/узкое окно: панели друг под другом
    body.classList.toggle("stacked", narrow);
    body.style.gridTemplateColumns = narrow ? "1fr" : `${L.lc ? 40 : L.left}px 8px minmax(300px, 1fr) 8px ${L.rc ? 40 : L.right}px`;
    center.style.gridTemplateRows = `minmax(120px, 1fr) 8px ${L.bc ? 38 : L.bottom}px`;
    $$("[data-collapse]", root).forEach(b => {
      const k = b.dataset.collapse, c = L[k];
      b.textContent = k === "lc" ? (c ? "⟩" : "⟨") : k === "rc" ? (c ? "⟨" : "⟩") : (c ? "⌃" : "⌄");
      b.title = c ? "развернуть" : "свернуть";
    });
    saveLayout(L);
    ide.editor && ide.editor.layout();
  }
  $$("[data-collapse]", root).forEach(b => b.onclick = () => { L[b.dataset.collapse] = !L[b.dataset.collapse]; applyLayout(); });
  $$(".gutter", root).forEach(g => g.onpointerdown = e => {
    e.preventDefault();
    g.classList.add("drag");
    g.setPointerCapture(e.pointerId);
    const k = g.dataset.g, start = { x: e.clientX, y: e.clientY, v: L[k] };
    const move = ev => {
      if (k === "left") { L.lc = false; L.left = Math.max(220, Math.min(800, start.v + ev.clientX - start.x)); }
      if (k === "right") { L.rc = false; L.right = Math.max(180, Math.min(600, start.v - (ev.clientX - start.x))); }
      if (k === "bottom") { L.bc = false; L.bottom = Math.max(100, Math.min(window.innerHeight - 220, start.v - (ev.clientY - start.y))); }
      applyLayout();
    };
    g.onpointermove = move;
    g.onpointerup = () => { g.classList.remove("drag"); g.onpointermove = null; };
  });
  applyLayout();
  const onResize = () => { if (document.body.contains(body)) applyLayout(); else window.removeEventListener("resize", onResize); };
  window.addEventListener("resize", onResize);

  // ---------- левая панель ----------
  const leftTabs = $("#left-tabs", root), leftBody = $("#left-body", root);
  ide.showLeft = id => {
    const t = cfg.leftTabs.find(x => x.id === id) || cfg.leftTabs[0];
    $$("button", leftTabs).forEach(b => b.classList.toggle("active", b.dataset.lt === t.id));
    leftBody.innerHTML = "";
    t.render(leftBody, ide);
  };
  leftTabs.innerHTML = cfg.leftTabs.map(t => `<button data-lt="${t.id}">${esc(t.label)}</button>`).join("");
  $$("button", leftTabs).forEach(b => b.onclick = () => { L.lc = false; applyLayout(); ide.showLeft(b.dataset.lt); });
  ide.showLeft(cfg.leftTab || cfg.leftTabs[0].id);
  cfg.buttons && cfg.buttons($("#ide-buttons", root), ide);

  // ---------- редактор ----------
  await loadMonaco();
  ide.editor = monaco.editor.create($("#monaco", root), {
    automaticLayout: true, fontFamily: "JetBrains Mono, Menlo, monospace", fontSize: 13.5, fontLigatures: false,
    minimap: { enabled: false }, scrollBeyondLastLine: false, tabSize: 4, insertSpaces: true, renderWhitespace: "selection",
    wordBasedSuggestions: "allDocuments", readOnly: !!cfg.readonly, model: null, padding: { top: 8 },
  });
  const uri = p => monaco.Uri.parse(`file:///${cfg.base.replace(/\W+/g, "_")}/${p}`);
  const lang = p => LANG[p.split(".").pop().toLowerCase()] || "plaintext";
  const rawUrl = p => `${cfg.base}/raw/${p.split("/").map(encodeURIComponent).join("/")}`;
  ide.rawUrl = rawUrl;

  async function loadModel(path) {
    if (ide.models[path]) return ide.models[path];
    const { content } = await api(`${cfg.base}/file?path=${encodeURIComponent(path)}`);
    const m = monaco.editor.getModel(uri(path)) || monaco.editor.createModel(content, lang(path), uri(path));
    m.setValue(content);
    ide.models[path] = m;
    ide.savedVersion[path] = m.getAlternativeVersionId();
    m.onDidChangeContent(() => { renderTabs(); scheduleSave(path); });
    return m;
  }
  const isDirty = p => ide.models[p] && ide.models[p].getAlternativeVersionId() !== ide.savedVersion[p];
  const saveTimers = {};
  function scheduleSave(path) {
    if (cfg.readonly) return;
    clearTimeout(saveTimers[path]);
    saveTimers[path] = setTimeout(() => ide.save(path), 1200);  // черновик сохраняется сам
  }
  ide.save = async (path = ide.current) => {
    if (!path || !ide.models[path] || cfg.readonly || !isDirty(path)) return;
    const m = ide.models[path], v = m.getAlternativeVersionId();
    try {
      await api(`${cfg.base}/file`, { method: "PUT", json: { path, content: m.getValue() } });
      ide.savedVersion[path] = v;
      renderTabs();
    } catch (e) { toast(`не сохранено ${path}: ${e.message}`, true); }
  };
  ide.saveAll = () => Promise.all(Object.keys(ide.models).map(p => ide.save(p)));

  function renderTabs() {
    $("#filetabs", root).innerHTML = ide.tabs.map(t => `<div class="filetab ${t.path === ide.current ? "active" : ""}" data-p="${esc(t.path)}" title="${esc(t.path)}">
        ${esc(t.path.split("/").pop())}${cfg.roles?.[t.path] === "given" ? '<span class="role">дан</span>' : ""}${t.kind === "diff" ? '<span class="role">diff с эталоном</span>' : ""}
        ${isDirty(t.path) ? '<span class="dirty" title="не сохранено"></span>' : ""}<span class="x" data-close="${esc(t.path)}">×</span></div>`).join("");
    $$(".filetab", root).forEach(el => el.onclick = e => {
      if (e.target.dataset.close) return closeTab(e.target.dataset.close);
      ide.open(el.dataset.p);
    });
    const sel = $("#ide-main", root);
    if (sel) {
      const py = Object.keys(ide.models).filter(p => p.endsWith(".py") && (!cfg.runnable || cfg.runnable(p)));
      const want = ide.mainChoice || "";
      sel.innerHTML = `<option value="">текущий файл</option>` + [...new Set([...(cfg.pyFiles || []), ...py])].filter(p => !cfg.runnable || cfg.runnable(p))
        .map(p => `<option value="${esc(p)}" ${p === want ? "selected" : ""}>${esc(p)}</option>`).join("");
    }
  }
  function closeTab(path) {
    ide.save(path);
    ide.tabs = ide.tabs.filter(t => t.path !== path);
    if (ide.current === path) ide.current = null;
    if (ide.tabs.length) ide.open(ide.tabs[ide.tabs.length - 1].path); else { ide.editor.setModel(null); showViewer(null); renderTabs(); }
  }
  function showViewer(html) {
    const v = $("#viewer", root);
    v.hidden = html == null;
    $("#monaco", root).style.visibility = html == null ? "visible" : "hidden";
    if (html != null) v.innerHTML = html;
    disposeDiff();
  }
  function disposeDiff() {
    if (ide.diffEditor) { ide.diffEditor.dispose(); ide.diffEditor = null; }
    if (ide.diffOrig) { ide.diffOrig.dispose(); ide.diffOrig = null; }
  }

  // Открыть файл: код — в редакторе, таблицы — превью, картинки/аудио/видео — просмотр
  ide.open = async (path, kindHint) => {
    let tab = ide.tabs.find(t => t.path === path);
    const ext = path.split(".").pop().toLowerCase();
    const kind = kindHint || (cfg.diffs && path in cfg.diffs ? "diff" : EDITABLE.test(path) ? "code"
      : ["csv", "tsv", "parquet", "xlsx", "xls", "json"].includes(ext) ? "table"
      : ["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext) ? "image" : ["mp4", "webm", "mov"].includes(ext) ? "video"
      : ["mp3", "wav", "ogg", "m4a", "flac"].includes(ext) ? "audio" : "code");
    if (!tab) { tab = { path, kind }; ide.tabs.push(tab); }
    ide.current = path;
    try {
      if (tab.kind === "code" || tab.kind === "text") {
        const m = await loadModel(path);
        showViewer(null);
        ide.editor.setModel(m);
        ide.editor.updateOptions({ readOnly: !!cfg.readonly });
        ide.editor.focus();
      } else if (tab.kind === "diff") {
        const mine = await loadModel(path);
        showViewer("");
        $("#viewer", root).style.padding = "0";
        const orig = ide.diffOrig = monaco.editor.createModel(cfg.diffs[path], "python");
        ide.diffEditor = monaco.editor.createDiffEditor($("#viewer", root), { automaticLayout: true, readOnly: true, fontLigatures: false,
          fontFamily: "JetBrains Mono, Menlo, monospace", fontSize: 13, minimap: { enabled: false }, renderSideBySide: true, originalEditable: false });
        ide.diffEditor.setModel({ original: orig, modified: mine });
      } else if (tab.kind === "table") {
        showViewer('<div class="muted spinner">читаю таблицу</div>');
        $("#viewer", root).style.padding = "";
        try {
          const t = await api(`${cfg.base}/table?path=${encodeURIComponent(path)}`);
          showViewer(`<div class="row" style="margin-bottom:8px"><b>${esc(path)}</b><span class="grow"></span><a href="${rawUrl(path)}?download=1">скачать</a></div>${tableHtml(t)}`);
        } catch (e) {
          showViewer(`<p class="err">${esc(e.message)}</p>${ext === "json" ? '<button id="as-text">открыть как текст</button>' : ""}`);
          const b = $("#as-text", root);
          if (b) b.onclick = () => { ide.tabs = ide.tabs.filter(t => t.path !== path); ide.open(path, "code"); };
        }
      } else {
        const tag = tab.kind === "image" ? `<img src="${rawUrl(path)}" alt="">` : tab.kind === "video" ? `<video src="${rawUrl(path)}" controls></video>` : `<audio src="${rawUrl(path)}" controls></audio>`;
        showViewer(`<div class="row" style="margin-bottom:8px"><b>${esc(path)}</b><span class="grow"></span><a href="${rawUrl(path)}?download=1">скачать</a></div>${tag}`);
      }
    } catch (e) { showViewer(`<p class="err">${esc(e.message)}</p>`); }
    renderTabs();
  };

  // Ctrl/Cmd+S — сохранить, Ctrl/Cmd+Enter — запустить текущий файл
  ide.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => ide.save());
  ide.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => ide.run());
  const onKey = e => {
    if (!document.body.contains(root.firstElementChild)) return document.removeEventListener("keydown", onKey);
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); ide.saveAll(); }
  };
  document.addEventListener("keydown", onKey);

  // ---------- консоль ----------
  const conBody = $("#con-body", root);
  ide.showConsole = tab => {
    L.bc = false; applyLayout();
    $$("[data-ct]", root).forEach(b => b.classList.toggle("active", b.dataset.ct === tab));
    $$("[data-cv]", root).forEach(v => { v.hidden = v.dataset.cv !== tab; });
    const ri = $("#repl-in", root);
    if (ri) ri.hidden = tab !== "repl";
    if (tab === "repl" && ri) $("textarea", ri).focus();
    ide.conTab = tab;
  };
  $$("[data-ct]", root).forEach(b => b.onclick = () => ide.showConsole(b.dataset.ct));
  $("#con-clear", root).onclick = () => {
    const v = $(`[data-cv="${ide.conTab || "out"}"]`, root);
    if (ide.conTab === "repl") $("#repl-log", root).innerHTML = ""; else if (ide.conTab !== "tests") v.innerHTML = "";
  };
  const scrollDown = () => { conBody.scrollTop = conBody.scrollHeight; };

  function runBlock(container, label) {
    const box = document.createElement("div");
    box.innerHTML = `<div class="run-head"><span>${label}</span><span class="spinner"></span><span data-st></span></div><div data-o></div>`;
    container.appendChild(box);
    return box;
  }
  async function follow(jobId, box) {
    const outEl = $("[data-o]", box);
    const r = await followJob(jobId, outs => { renderOutputs(outEl, outs, rawUrl); scrollDown(); }, () => ide.alive);
    const st = r.result?.status;
    $(".spinner", box)?.remove();
    $("[data-st]", box).innerHTML = st === "ok" ? `<span class="ok">✓ ${fmtMs(r.result.ms)}</span>` : st === "interrupted" ? '<span class="warn">остановлено</span>'
      : st === "timeout" ? '<span class="err">лимит времени</span>' : st ? '<span class="err">ошибка</span>' : "";
    if (!r.outputs.length && st === "ok") outEl.innerHTML = '<span class="muted">(нет вывода)</span>';
    scrollDown();
    refreshTree();
    return r;
  }

  ide.run = async path => {
    if (!cfg.run || cfg.readonly) return;
    const sel = $("#ide-main", root);
    path = path || (sel && sel.value) || ide.current;
    if (!path || !path.endsWith(".py") || (cfg.runnable && !cfg.runnable(path))) return toast("откройте .py файл или выберите главный файл", true);
    await ide.saveAll();
    ide.showConsole("out");
    const outView = $('[data-cv="out"]', root);
    if (!ide.outRuns++) outView.innerHTML = "";
    const box = runBlock(outView, `▶ ${esc(path)} · ${new Date().toLocaleTimeString()}`);
    try { await follow(await cfg.run(path), box); } catch (e) { $("[data-o]", box).innerHTML = `<pre class="o-text stderr">${esc(e.message)}</pre>`; $(".spinner", box)?.remove(); }
  };
  ide.check = async () => {
    if (!cfg.check || cfg.readonly) return;
    await ide.saveAll();
    ide.showConsole("tests");
    const tv = $('[data-cv="tests"]', root);
    tv.innerHTML = '<div class="run-head"><span>тесты</span><span class="spinner"></span></div><div data-o></div>';
    const btn = $("#ide-check", root);
    if (btn) btn.disabled = true;
    try {
      const jobId = await cfg.check();
      const r = await followJob(jobId, outs => { renderOutputs($("[data-o]", tv), outs, rawUrl); scrollDown(); }, () => ide.alive);
      ide.lastCheck = r.result?.check;
      tv.innerHTML = testsHtml(ide.lastCheck) + `<details class="mt"><summary class="muted small">вывод pytest</summary><div data-o></div></details>`;
      renderOutputs($("[data-o]", tv), r.outputs, rawUrl);
      cfg.onCheck && cfg.onCheck(ide.lastCheck);
      return ide.lastCheck;
    } catch (e) { tv.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
    finally { if (btn) btn.disabled = false; }
  };
  ide.showTests = check => { $('[data-cv="tests"]', root).innerHTML = testsHtml(check); };

  const replIn = $("#repl-in textarea", root);
  if (replIn) {
    const hist = [];
    let hi = 0;
    const grow = () => { replIn.style.height = "auto"; replIn.style.height = Math.min(160, replIn.scrollHeight) + "px"; };
    replIn.oninput = grow;
    replIn.onkeydown = async e => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const code = replIn.value;
        if (!code.trim()) return;
        hist.push(code); hi = hist.length;
        replIn.value = ""; grow();
        const box = runBlock($("#repl-log", root), `<span class="mono">&gt;&gt;&gt; ${esc(code.length > 300 ? code.slice(0, 300) + "…" : code)}</span>`);
        scrollDown();
        try { await follow(await cfg.exec(code), box); } catch (err) { $("[data-o]", box).innerHTML = `<pre class="o-text stderr">${esc(err.message)}</pre>`; }
      } else if (e.key === "ArrowUp" && !replIn.value.includes("\n") && hist.length) {
        e.preventDefault(); hi = Math.max(0, hi - 1); replIn.value = hist[hi]; grow();
      } else if (e.key === "ArrowDown" && !replIn.value.includes("\n") && hist.length) {
        e.preventDefault(); hi = Math.min(hist.length, hi + 1); replIn.value = hist[hi] || ""; grow();
      }
    };
  }

  const runBtn = $("#ide-run", root);
  if (runBtn) {
    runBtn.onclick = () => ide.run();
    $("#ide-stop", root).onclick = () => cfg.stop && cfg.stop();
    $("#ide-main", root).onchange = e => { ide.mainChoice = e.target.value; };
    ide.mainChoice = cfg.main || "";
  }
  const checkBtn = $("#ide-check", root);
  if (checkBtn) checkBtn.onclick = () => ide.check();

  // ---------- дерево файлов ----------
  const tree = $("#tree", root);
  const expanded = new Set(["", ...(cfg.expand || [])]);
  let selected = null;
  async function renderDir(el, path, depth) {
    let items;
    try { items = await api(`${cfg.base}/files?path=${encodeURIComponent(path)}`); }
    catch (e) { el.innerHTML = `<div class="err small" style="padding:4px 10px">${esc(e.message)}</div>`; return; }
    el.innerHTML = items.length ? "" : `<div class="muted small" style="padding:2px ${depth * 14 + 26}px">пусто</div>`;
    for (const it of items) {
      const row = document.createElement("div");
      row.className = "trow" + (it.path === selected ? " sel" : "");
      row.style.paddingLeft = 8 + depth * 14 + "px";
      const open = it.dir && expanded.has(it.path);
      row.innerHTML = `<span class="ico ${it.kind}">${it.dir ? (open ? "▾" : "▸") : FILE_ICON[it.kind] || "·"}</span>
        <span class="name" title="${esc(it.link ? `${it.path} → ${it.link}` : it.path)}">${esc(it.name)}${it.link ? ' <span class="muted">⛓</span>' : ""}</span>
        <span class="muted small">${it.dir ? "" : fmtSize(it.size)}</span>
        ${cfg.readonly ? "" : `<span class="acts"><button data-a="ren" title="переименовать">✎</button><button data-a="del" title="удалить">✕</button></span>`}`;
      el.appendChild(row);
      const kids = document.createElement("div");
      el.appendChild(kids);
      if (open) await renderDir(kids, it.path, depth + 1);
      row.onclick = async e => {
        const act = e.target.closest("[data-a]")?.dataset.a;
        if (act === "ren") return renameItem(it);
        if (act === "del") return deleteItem(it);
        selected = it.path;
        $$(".trow.sel", tree).forEach(r => r.classList.remove("sel")); row.classList.add("sel");
        if (it.dir) {
          if (expanded.has(it.path)) { expanded.delete(it.path); kids.innerHTML = ""; row.querySelector(".ico").textContent = "▸"; }
          else { expanded.add(it.path); row.querySelector(".ico").textContent = "▾"; await renderDir(kids, it.path, depth + 1); }
        } else ide.open(it.path);
      };
      row.ondragover = e => { if (it.dir) { e.preventDefault(); e.stopPropagation(); row.classList.add("sel"); } };
      row.ondragleave = () => row.classList.remove("sel");
      row.ondrop = e => { if (it.dir) { e.preventDefault(); e.stopPropagation(); uploadFiles([...e.dataTransfer.files], it.path); } };
    }
  }
  const targetDir = () => {
    if (!selected) return "";
    return ide.dirOf(selected);
  };
  ide.dirOf = p => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");
  async function refreshTree() {
    const scroll = tree.scrollTop;
    await renderDir(tree, "", 0);
    tree.scrollTop = scroll;
  }
  ide.refreshTree = refreshTree;
  async function renameItem(it) {
    const name = prompt("Новое имя", it.path);
    if (!name || name === it.path) return;
    try {
      await ide.save(it.path);
      await api(`${cfg.base}/rename`, { method: "POST", json: { path: it.path, new_path: name } });
      if (ide.models[it.path]) { ide.models[it.path].dispose(); delete ide.models[it.path]; ide.tabs = ide.tabs.filter(t => t.path !== it.path); }
      refreshTree();
    } catch (e) { toast(e.message, true); }
  }
  async function deleteItem(it) {
    const warn = (it.path === "data" || it.path.startsWith("data/")) && cfg.dataLink ? "\nВНИМАНИЕ: data/ — это ваша папка на диске, файл удалится с диска." : "";
    if (!confirm(`Удалить ${it.path}?${warn}`)) return;
    try {
      await api(`${cfg.base}/files?path=${encodeURIComponent(it.path)}`, { method: "DELETE" });
      if (ide.models[it.path]) { ide.tabs = ide.tabs.filter(t => t.path !== it.path); ide.models[it.path].dispose(); delete ide.models[it.path]; if (ide.current === it.path) closeTab(it.path); }
      refreshTree();
    } catch (e) { toast(e.message, true); }
  }
  async function uploadFiles(files, folder) {
    if (!files.length) return;
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    fd.append("folder", folder || "");
    try { const r = await api(`${cfg.base}/upload`, { method: "POST", body: fd }); toast(`загружено: ${r.saved.join(", ")}`); expanded.add(folder || ""); refreshTree(); }
    catch (e) { toast(e.message, true); }
  }
  tree.ondragover = e => { if (!cfg.readonly) { e.preventDefault(); tree.classList.add("over"); } };
  tree.ondragleave = () => tree.classList.remove("over");
  tree.ondrop = e => { e.preventDefault(); tree.classList.remove("over"); if (!cfg.readonly) uploadFiles([...e.dataTransfer.files], targetDir()); };
  $$("[data-tt]", root).forEach(b => b.onclick = async () => {
    const t = b.dataset.tt;
    if (t === "refresh") return refreshTree();
    if (t === "upload") return $("#tree-up", root).click();
    if (t === "bind") return cfg.bindData(ide);
    const base = targetDir();
    const name = prompt(t === "dir" ? "Имя папки" : "Имя файла (например utils.py)", base ? base + "/" : "");
    if (!name) return;
    try {
      await api(`${cfg.base}/new`, { method: "POST", json: { path: name, dir: t === "dir" } });
      expanded.add(ide.dirOf(name));
      await refreshTree();
      if (t === "file") ide.open(name);
    } catch (e) { toast(e.message, true); }
  });
  $("#tree-up", root).onchange = e => { uploadFiles([...e.target.files], targetDir()); e.target.value = ""; };
  $("#data-note", root).innerHTML = cfg.dataLink ? `data/ ⛓ <span class="mono">${esc(cfg.dataLink)}</span>` : "перетащите файлы на дерево, чтобы загрузить";
  refreshTree();

  for (const p of cfg.preload || []) loadModel(p).catch(() => {});  // имена из файлов задачи — в автодополнение
  for (const p of cfg.open || []) await ide.open(p);
  ide.dispose = () => {
    ide.alive = false;
    ide.saveAll();
    disposeDiff();  // сначала редакторы, потом модели — иначе Monaco ругается
    ide.editor && ide.editor.dispose();
    Object.values(ide.models).forEach(m => m.dispose());
    document.body.classList.remove("ide-mode");
  };
  return ide;
}
