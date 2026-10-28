"""Запуск: python content/tools/docs_shots.py http://127.0.0.1:8000 '{"recall": id, "baseline": id, "attempt": id, "review": id}' [имена снимков через запятую]
Снимки для docs/ИНСТРУКЦИЯ.md: Playwright 1440×900, тёмная тема; Pillow — красные кружки с номерами и стрелки.
Подписи «1 — …» вписываются в инструкцию вместо <!-- shot:имя -->."""
import json, math, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

BASE = sys.argv[1]  # http://127.0.0.1:8003
IDS = json.loads(sys.argv[2])  # {recall, baseline, attempt, review}
ROOT = Path("/Users/nakhvamdis-ka/Documents/T./docs")
IMG = ROOT / "img"
IMG.mkdir(parents=True, exist_ok=True)
RED = (240, 72, 62)
FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 17)

# находим узел холста по имени карточки
NODE = "[...document.querySelectorAll('.drawflow-node')].find(n => n.querySelector('.cn-title')?.textContent.trim() === '{}')"


def node(name):
    return NODE.format(name)


def q(sel):
    return f"document.querySelector({json.dumps(sel)})"


def btn(text):
    return f"[...document.querySelectorAll('button')].find(b => b.textContent.trim().startsWith({json.dumps(text)}))"


SHOTS = [
    ("01-wall", f"#/builder/{IDS['baseline']}", None, [
        (node("conv2d"), "кирпичик — маленькая задача на одну вещь (conv2d)"),
        (node("conv_block"), "блок — собран из кирпичиков (conv_block = conv2d + batch_norm + relu + max_pool2d)"),
        (q(".bf-frame-h"), "стена — целый проект: рамка вокруг всех карточек"),
        (q(".bf-slot"), "слот — сюда подходит любая реализация (здесь — оптимизатор adam или sgd)"),
        (q(".drawflow-node .ms"), "статус двух режимов: книга — «Библиотека», шестерёнка — «С нуля»"),
        (q(".connection .main-path"), "стрелка ведёт от используемого к использующему"),
    ]),
    ("02-menu", "#/today", None, [
        (q("nav a[data-r=today]"), "Сегодня — что повторить сегодня"),
        (q("nav a[data-r=tasks]"), "Задачи — все задачи, дерево тем, фильтры"),
        (q("nav a[data-r=map]"), "Карта — карта навыков"),
        (q("nav a[data-r=builder]"), "Конструктор — визуальная доска для задач"),
        (q("nav a[data-r=journal]"), "Журнал — все попытки"),
        (q("nav a[data-r=stats]"), "Статистика"),
        (q("nav a[data-r=settings]"), "Настройки"),
        (q("#streak"), "серия: дней подряд со сданной попыткой"),
        (q(".help-btn"), "«?» — эта инструкция"),
        (q("#theme"), "тема: тёмная → светлая → как в системе"),
    ]),
    ("03-today", "#/today", None, [
        (q("h1.big"), "сколько задач на сегодня и примерно сколько минут"),
        (q(".today-head .row"), "просрочено, по плану, новые и сколько в каждом режиме"),
        (q("#go-first"), "начать первую задачу списка"),
        (q(".tcard"), "список: имя, причина, режим, уровень, категория, статус"),
        (q(".trow2 .mb"), "режим строки: «Библиотека» или «С нуля»"),
        (q(".hint"), "подсказка: что сделать сначала"),
    ]),
    ("03-task", f"#/task/{IDS['recall']}", {"full": 1500}, [
        (q(".mode-card[data-mode=library]"), "карточка «Библиотека»: статус, лучшая оценка, следующий повтор; клик — выбрать режим"),
        (q(".mode-card[data-mode=scratch]"), "карточка «С нуля» — то же для режима «С нуля»"),
        (q("#go"), "начать в выбранном режиме"),
        (q(".task-page .tabs"), "README, попытки, состав, версии, настройки задачи"),
        (q(".rcard:not(.how) header"), "«Как применять»: готовая функция, параметры, подводные камни"),
        (q(".rcard.how header"), "«Как работает»: идея, формула, шаги и правила режима"),
    ]),
    ("04-ide", f"#/attempt/{IDS['active']}", {"ide": True, "check": True}, [
        (q("#left-tabs"), "описание задачи, попытки, эталон"),
        (q("#filetabs"), "вкладки файлов: иконка — режим файла"),
        (q(".view-overlays .err-line"), "строка с ошибкой подсвечена прямо в коде, с подписью"),
        (q("#tree"), "файлы попытки: свои, bricks/, data/, results/"),
        (q("#con-tabs"), "Вывод, Тесты, Консоль"),
        (q(".t-row.fail"), "упавший тест: «ожидалось / получено»"),
        (q("[data-loc]"), "«строка N» — открыть место в коде"),
        (q(".t-modes > summary"), "«Проверки режима»: как написан код, а не что он делает"),
        (q("#ide-run"), "Запустить (⌘↵)"),
        (q("#ide-check"), "Проверить (⇧⌘↵) — тесты, попытка не засчитывается"),
        (q("#submit"), "Сдать — финальный прогон и оценка"),
        (q("#statusbar"), "строка состояния: Python, пакеты, правило режима, курсор"),
    ]),
    ("05-assemble", f"#/assemble/{IDS['baseline']}/scratch", None, [
        (q(".as-board .src-pill"), "источник кирпичика — выбирается на карточке"),
        (q(".as-leg"), "что значит каждый источник"),
        (q("[data-all=ref]"), "быстро: всё эталоном / всё сам / как в прошлый раз"),
        (q(".as-self"), "что вы пишете сами и в каком режиме"),
        (q("#as-go"), "Начать"),
    ]),
    ("06-report", f"#/attempt/{IDS['attempt']}", {"full": 1700}, [
        (q(".ring-box"), "оценка из 100"),
        (q(".rp-score [data-g]"), "уровень повторения; нажмите другой, если не согласны"),
        (q(".rp-nodes"), "по узлам: тесты каждого кирпичика и режим"),
        (q(".rp-tiles"), "время, «Проверить», эталон, графики по попыткам"),
        (q(".rp-diff .seg"), "сравнение с эталоном: по смыслу / как написано"),
        (q("#rp-work"), "Работа над ошибками"),
    ]),
    ("07-review", f"#/review/{IDS['review']}", None, [
        (q(".stepper"), "три шага: смотрю → переписываю → по памяти"),
        (q(".sem-cols"), "эталон и ваш код, отличия по смыслу подсвечены"),
        (q("#next"), "к следующему шагу"),
    ]),
    ("08-journal", "#/journal", None, [
        (q(".jr-filters"), "фильтры: режим, брошенные, с ошибками, работа над ошибками"),
        (q(".jr-table tbody tr"), "строка: дата, задача, режим, статус, оценка, время — клик откроет"),
        (q(".jr-why"), "что пошло не так"),
    ]),
    ("08-stats", "#/stats", {"full": 1200}, [
        (q(".st-top .card"), "серия и рекорд"),
        (q(".st-act"), "активность за 12 недель"),
        (q(".st-vs-h"), "«Библиотека против с нуля»: доля выученных по категориям"),
        (q(".st-bottom"), "слабые темы, слабые кирпичики, график по задаче"),
    ]),
    ("08-map", "#/map", None, [
        (q(".cov-card"), "сколько создано и выучено в каждом режиме"),
        (q(".legend-row"), "цвета статусов"),
        (q("table.map thead"), "категории кирпичиков"),
        (q(".mchip:not(.ghost-chip)"), "чип: слева библиотека, справа с нуля"),
        (q(".ghost-chip"), "бледный пунктир — «план»: задачи ещё нет"),
    ]),
    ("09-builder-empty", "#/builder", None, [
        (q(".tpl-grid"), "шаблоны новых задач — черновики для обоих режимов"),
        (q(".pal-tabs"), "палитра: дерево тем или карта навыков"),
        (q(".pal-search"), "поиск кирпичика — перетащите его на холст"),
        (q("#bf-check"), "Проверить всё — эталоны всех карточек"),
        (q("#bf-save"), "Сохранить: черновики станут задачами, стрелки — зависимостями"),
        (q(".bf-zoom"), "масштаб и «показать всё»"),
    ]),
    ("09-builder-block", f"#/builder/{IDS['baseline']}", {"block": ["stratified_split", "class_weights"]}, [
        (q(".bf-selbox"), "выделено Shift+кликом"),
        (q(".bf-selbar"), "Собрать в блок (⌘G) и Выровнять"),
        (q("#bf-blockname"), "имя нового блока"),
        (q("#bf-doblock"), "создать задачу-блок с выбранными зависимостями"),
    ]),
    ("09-builder-cycle", f"#/builder/{IDS['baseline']}", {"cycle": ["pipeline", "conv_block"]}, [
        (q(".bf-cyc-label"), "стрелка замкнула круг: подпись «Цикл: A → B → A»"),
        (q(".alert.err"), "почему так нельзя"),
        (q("#bf-unlink"), "Удалить связь"),
        (q("#bf-flip"), "Развернуть направление"),
        (q("#bf-status"), "пока цикл есть — сохранится только раскладка"),
    ]),
    ("09-editor", f"#/edit/{IDS['recall']}", {"ide": True, "expand": True}, [
        (q("#tree"), "папка задачи: description.md, reference/library, reference/scratch, tests, task.json, data/"),
        (q("#filetabs"), "открытый эталон"),
        (q("#ide-check"), "Проверить — тесты на эталоне из папки"),
        (btn("Сохранить версию"), "Сохранить версию — новые попытки пойдут по ней"),
        (btn("Вынести в кирпичик"), "Вынести в кирпичик / Создать слот"),
    ]),
    ("10-tests", f"#/builder/{IDS['recall']}", {"tests": "recall"}, [
        (q(".insp-tabs [data-itab=tests]"), "вкладка «Тесты» инспектора"),
        (q(".t2-head"), "прогон на обоих эталонах: колонка «Библиотека» и колонка «С нуля»"),
        (q(".t2-row"), "тест и результат на каждом эталоне"),
        (q("#bf-runall"), "прогнать снова"),
        (q("#bf-newtest"), "добавить файл теста"),
    ]),
    ("11-settings", "#/settings", {"scroll": "#sec-bk"}, [
        (q("#bk-auto"), "автокопии — раз в день, 7 последних"),
        (q("#bk-man"), "ручные копии — отдельная папка, не удаляются сами"),
        (q("#bk-now"), "сделать копию сейчас"),
        (q("#sec-map .drop"), "импорт карты навыков: перетащите combinations.csv"),
        (q(".fmt"), "пример формата"),
    ]),
    ("12-dup", f"#/task/{IDS['recall']}", None, [
        (q("#dup"), "Дублировать — спрашивает название новой задачи"),
        (q(".task-head a[href^='#/edit']"), "Редактировать — файлы задачи"),
        (q(".task-head a[href^='#/builder']"), "Открыть в конструкторе"),
    ]),
]


def new_attempt():
    import urllib.request as u
    api = BASE + "/api"
    def req(m, p, b=None):
        r = u.Request(api + p, method=m, data=json.dumps(b).encode() if b is not None else None, headers={"Content-Type": "application/json"})
        return json.load(u.urlopen(r))
    a = req("POST", f"/tasks/{IDS['recall']}/attempts", {"mode": "scratch", "assembly": {"confusion_matrix": {"source": "ref"}}})
    code = req("GET", f"/attempts/{IDS['attempt']}/file?path=solution.py")["content"]
    req("PUT", f"/attempts/{a['id']}/file", {"path": "solution.py", "content": code})
    return a["id"]


def arrow(d, a, b):
    d.line([a, b], fill=RED, width=4)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for s in (-0.45, 0.45):
        d.line([b, (b[0] - 16 * math.cos(ang + s), b[1] - 16 * math.sin(ang + s))], fill=RED, width=4)


def annotate(path, boxes):
    im = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(im)
    W, H = im.size
    for i, bx in enumerate(boxes, 1):
        x, y, w, h = bx["x"], bx["y"], bx["width"], bx["height"]
        tx, ty = x + min(w / 2, 36), y + min(h / 2, 16)  # куда указать
        cx, cy = tx - 62, ty - 46  # кружок — выше и левее цели
        if cx < 22: cx = tx + 62
        if cy < 22: cy = ty + 50
        cx, cy = min(max(cx, 22), W - 22), min(max(cy, 22), H - 22)
        d.rectangle([x - 3, y - 3, x + w + 3, y + h + 3], outline=RED, width=3)
        arrow(d, (cx, cy), (tx, ty))
        d.ellipse([cx - 17, cy - 17, cx + 17, cy + 17], fill=RED, outline=(255, 255, 255), width=2)
        t = str(i)
        tw = d.textlength(t, font=FONT)
        d.text((cx - tw / 2, cy - 10), t, fill=(255, 255, 255), font=FONT)
    im.save(path)


def main():
    captions = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark", device_scale_factor=1)
        page.on("dialog", lambda d: d.accept())  # уход из попытки и холста — без вопросов
        page.add_init_script("try { localStorage.setItem('theme', 'dark'); localStorage.setItem('code.fs', '13'); } catch (e) {}")
        page.goto(BASE + "/#/today")
        page.wait_for_timeout(2500)
        only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
        for name, route, opt, notes in SHOTS:
            if only and name not in only:
                captions[name] = json.loads((IMG / f"{name}.json").read_text()) if (IMG / f"{name}.json").exists() else []
                continue
            opt = opt or {}
            page.evaluate("() => { if (window.current && current.leaveGuard) current.leaveGuard = null; }")
            if opt.get("check"):  # свежая активная попытка: перезагрузка закрыла бы её как брошенную
                route = f"#/attempt/{new_attempt()}"
                page.goto(BASE + "/#/today"); page.reload(); page.wait_for_timeout(2000)
                page.goto(BASE + "/" + route)
            else:
                page.goto(BASE + "/" + route)
                page.reload()
            page.wait_for_timeout(7000 if "builder" in route else 4500)
            if opt.get("check"):  # «Проверить» в активной попытке — тесты и подсветка строки с ошибкой
                page.click("#ide-check")
                page.wait_for_selector(".t-group", timeout=120000)
                page.evaluate("() => current.open('solution.py')")
                page.wait_for_timeout(1500)
                page.evaluate("() => { document.querySelector('#con-body').scrollTop = 0; }")
                page.wait_for_timeout(300)
            if opt.get("block"):
                page.evaluate("""names => { for (const n of names) { const el = [...document.querySelectorAll('.drawflow-node')].find(x => x.querySelector('.cn-title')?.textContent.trim() === n).querySelector('.drawflow_content_node');
                  const r = el.getBoundingClientRect(); el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, shiftKey: true, clientX: r.x + 30, clientY: r.y + 20 })); document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true })); } }""", opt["block"])
                page.wait_for_timeout(600)
            if opt.get("cycle"):
                page.evaluate("""([a, b]) => { const f = n => [...document.querySelectorAll('.drawflow-node')].find(x => x.querySelector('.cn-title')?.textContent.trim() === n);
                  const o = f(a).querySelector('.output'), i = f(b).querySelector('.input'), ro = o.getBoundingClientRect(), ri = i.getBoundingClientRect();
                  o.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: ro.x + 4, clientY: ro.y + 4 }));
                  document.querySelector('.drawflow').dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: ri.x + 4, clientY: ri.y + 4 }));
                  i.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: ri.x + 4, clientY: ri.y + 4 })); }""", opt["cycle"])
                page.wait_for_timeout(800)
            if opt.get("tests"):
                page.evaluate("""n => { const el = [...document.querySelectorAll('.drawflow-node')].find(x => x.querySelector('.cn-title')?.textContent.trim() === n).querySelector('.drawflow_content_node');
                  const r = el.getBoundingClientRect(); el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: r.x + 30, clientY: r.y + 20 })); document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true })); }""", opt["tests"])
                page.wait_for_timeout(1200)
                page.evaluate("document.querySelector('[data-itab=tests]').click()")
                page.wait_for_timeout(1000)
                page.evaluate("document.querySelector('#bf-runall').click()")
                page.wait_for_selector(".t2-row", timeout=120000)
                page.wait_for_timeout(800)
            if opt.get("expand"):
                for d in ("reference", "tests"):
                    page.evaluate(f"""() => {{ const r = [...document.querySelectorAll('#tree .trow')].find(x => x.querySelector('.name')?.textContent.trim() === '{d}/'); r && r.click(); }}""")
                    page.wait_for_timeout(700)
            if opt.get("scroll"):
                page.evaluate(f"document.querySelector({json.dumps(opt['scroll'])}).scrollIntoView({{block: 'start'}})")
                page.wait_for_timeout(600)
            full = opt.get("full")
            if full:
                page.set_viewport_size({"width": 1440, "height": full})
                page.wait_for_timeout(1200)
            boxes, caps = [], []
            for expr, cap in notes:
                bx = page.evaluate(f"() => {{ const el = {expr}; if (!el) return null; const r = el.getBoundingClientRect(); return r.width ? {{x: r.x, y: r.y, width: r.width, height: r.height}} : null; }}")
                if bx and bx["y"] < (full or 900) and bx["y"] + bx["height"] > 0:
                    boxes.append(bx); caps.append(cap)
                else:
                    print(f"  {name}: не найдено на экране — «{cap}»")
            path = IMG / f"{name}.png"
            page.screenshot(path=str(path))
            annotate(path, boxes)
            captions[name] = caps
            (IMG / f"{name}.json").write_text(json.dumps(caps, ensure_ascii=False))
            print(name, len(boxes), "отметок")
            if full:
                page.set_viewport_size({"width": 1440, "height": 900})
        b.close()
    src = (ROOT / "ИНСТРУКЦИЯ.src.md").read_text(encoding="utf-8")
    def sub(m):
        name = m.group(1)
        caps = captions.get(name)
        if caps is None:
            return ""
        return f"![{name}](img/{name}.png)\n\n" + "\n".join(f"**{i}** — {c}  " for i, c in enumerate(caps, 1)) + "\n"
    (ROOT / "ИНСТРУКЦИЯ.md").write_text(re.sub(r"<!-- shot:([\w-]+) -->", sub, src), encoding="utf-8")
    print("готово:", ROOT / "ИНСТРУКЦИЯ.md")


main()
