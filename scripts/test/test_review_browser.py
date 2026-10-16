"""Optional browser/interface smoke: the real page driven through the review surface (no plugin host).

要证明的事（B8.3 ＋ B8.4c 的验收）：
  ① 页面加载时注入点已被换成桥的地址（页面里不带桥的副本）；桥声明了 `asset-upload`，控件按它显示；
  ② 一处框选 + 一次逐页提交 → feedback.json 落盘（含上传件）**且** wake 被调用（带 page_key）；
  ③ 陈旧提交被拒：模型重出那一页之后再提交 → 页面提示「这一页已更新，先复核」，不写文件；
  ④ 整套提交用**整句覆盖**唤醒（`{unit:'整套', text:…}`），不是 surface 的逐页模板；
  ⑤ 模型重出一页 → 宿主戳 → 页面**自己换图**：不重载、不丢人写的东西、之后提交不 stale。
All approvals below are synthetic test data.
"""
import hashlib
import json
import os
import sys
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_v5 as fixtures  # noqa: E402
from project_state import PNG, REVIEW, SVG, approved, read, write  # noqa: E402
import workbench_store  # noqa: E402
from ppt_pipeline import check, export, make_review, next_action, resolve  # noqa: E402
from review_feedback import consume  # noqa: E402
from ppt_pipeline import unresolved  # noqa: E402
import review_surface  # noqa: E402
from lib.planners_modules import resolve_module  # noqa: E402
sys.path.insert(0, str(resolve_module('planners-review-core') / 'scripts' / 'lib'))
import review_host  # noqa: E402  （宿主生命周期只有公共模组那一份）


@unittest.skipUnless(os.environ.get('PPT_BROWSER_TESTS') == '1', 'set PPT_BROWSER_TESTS=1 for local browser/interface smoke')
class ReviewBrowserTests(unittest.TestCase):
    def wire(self, page):
        """把页面与宿主之间**真的发生过的请求**记下来（报告里要给出请求/响应）。"""
        self.exchanges = []

        def on_request(request):
            if '/__review/' in request.url:
                parts = urlsplit(request.url)
                self.exchanges.append(['→', request.method, parts.path + ('?' + parts.query if parts.query else ''),
                                       (request.post_data or '')[:200]])

        def on_response(response):
            if '/__review/' in response.url:
                self.exchanges.append(['←', response.status, urlsplit(response.url).path, ''])

        page.on('request', on_request)
        page.on('response', on_response)

    def submit_page(self, page, label):
        """点一次逐页提交并等到它真的走完。

        先把状态条清空：`#message` 里还留着上一页那句话，直接等它会在**下一次提交之前**就返回
        （第一版踩过：omega 那次点击被 race 掉，文件里还是 pending）。
        """
        page.evaluate("() => { document.querySelector('#message').textContent = '' }")
        page.get_by_text(label, exact=True).click()
        # 提示有三档（宿主已核对 / 宿主未核对 / 同一次提交重发），共同点只有"已写入"——等它，
        # 不要等某一档的措辞，否则换一档就会在这里超时（第一版就踩了）。
        page.wait_for_function("document.querySelector('#message').textContent.includes('已写入')")

    def submit_batch(self, page, label='提交已有决定'):
        page.evaluate("() => { document.querySelector('#message').textContent = '' }")
        page.get_by_text(label, exact=True).click()
        page.wait_for_function("() => { const d = document.querySelector('#submitDialog'); return d && !d.open }")

    def posts(self, suffix):
        return [item for item in self.exchanges if item[0] == '→' and item[1] == 'POST' and item[2].startswith(suffix)]

    def test_real_browser_review_through_the_surface(self):
        """真人从浏览器走完整一轮 —— 按**当前工作台契约**跑。

        要证明的事：
          ① 上传一张图 → 走桥、落进项目、进本页状态；页面上选的显示方式与对齐也要随提交交出去；
          ② 框选一处 + 写批注 → 画布上真的有框，文字进状态；
          ③ 逐页提交 → 落成 store 任务（带批注、图片与图片设定）**且**唤醒模型（`unit=page_key`）；
          ④ 宿主侧已经前进一版之后再提交 → 被拒（不许把陈旧意见写进去），人写的字不丢。

        2026-10-16：这一条原先跑的是旧「整套 PPT 审阅」面（`feedback.json` 的 pages/decision、
        标签「框选问题」「保存标注」「本页要求修改」）。那些控件在当前页面里已经不存在 ——
        用户故事不变，机制改成按现状跑；旧流程的其余行为由 `test_workbench_tools` /
        `test_workbench_ui` 同名行为覆盖（任务、唤醒、陈旧拒写、上一轮只读）。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            state = review_host.start_host(root / review_surface.SURFACE_REL); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                self.wire(page)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.wait_for_function("typeof canCommand!=='undefined'&&canCommand&&recoveryReady")
                page.wait_for_selector('#rail button[data-key]')
                page.wait_for_timeout(1200)   # 等启动那次宿主同步落定（它会在飞行中重画一次页面）
                key = page.evaluate('() => pageOrder[0]')

                # ① 上传：桥负责落盘，页面只记 rel
                page.locator('#newFile').set_input_files(str(root / PNG / (key + '.png')))
                page.wait_for_selector('.asset')
                rel = page.evaluate('(k) => state[k].assets[0].path', key)
                self.assertTrue(rel.startswith('_internal/05_review/uploads/' + key + '/'), rel)
                self.assertTrue((root / rel).is_file(), '上传件必须真的落在项目里')
                self.assertEqual(page.evaluate('(k) => state[k].assets[0].sha256', key),
                                 hashlib.sha256((root / rel).read_bytes()).hexdigest())
                # 图片的三个设定：显示方式与对齐要留在控件上，并随提交出去
                page.locator('#assets .seg button[data-value=cover]').click()
                page.locator('#assets .grid9 button[data-value="bottom-right"]').click()

                # ② 框选一处 + 添加批注
                page.get_by_text('框选', exact=True).click()
                box = page.locator('#preview').bounding_box()
                page.mouse.move(box['x'] + box['width'] * .1, box['y'] + box['height'] * .1)
                page.mouse.down()
                page.mouse.move(box['x'] + box['width'] * .4, box['y'] + box['height'] * .4)
                page.mouse.up()
                page.locator('#regionNote').fill('标题压到了图')
                page.get_by_text('添加批注', exact=True).click()
                self.assertEqual(page.locator('.annotation').count(), 1, '框选要真的画出来')
                page.locator('#feedback').fill('顺便把副标题删掉')

                # ③ 逐页提交。本地宿主是 http，页面按契约只允许它提交整套（`pageDispatch` 不露出）；
                # 侧栏宿主（postMessage）才有逐页提交。这里把 transport 标成侧栏宿主，
                # 走的仍是页面里同一个 `dispatchFeedback('page')` 入口与同一条 store 命令。
                page.evaluate("() => { review.transport='postMessage' }")
                before = set(workbench_store.ensure(root)['tasks'])
                self.assertTrue(page.evaluate("() => dispatchFeedback('page')"))
                page.wait_for_function('(k) => state[k].task!==null', arg=key)
                created = {tid: task for tid, task in workbench_store.ensure(root)['tasks'].items()
                           if tid not in before}
                self.assertEqual(len(created), 1, '逐页提交必须落一条任务')
                task = list(created.values())[0]
                self.assertEqual(list(task['pages']), [key], '逐页任务的页集合只能是这一页')
                self.assertEqual(task['pages'][key]['feedback'], '顺便把副标题删掉')
                self.assertEqual([a['text'] for a in task['pages'][key]['annotations']], ['标题压到了图'])
                self.assertEqual(len(task['pages'][key]['assets']), 1, '上传件要随任务交出去')
                self.assertEqual(task['pages'][key]['assets'][0]['fit'], 'cover', '页面上选的显示方式要进任务')
                self.assertEqual(task['pages'][key]['assets'][0]['anchor'], 'bottom-right', '九宫格选的角要进任务')
                wake_posts = self.posts('/__review/wake')
                self.assertTrue(wake_posts, '逐页提交必须唤醒模型')
                self.assertIn('"unit":"' + key + '"', wake_posts[0][3].replace(' ', ''))
                rows = [json.loads(line) for line in
                        (root / review_surface.WAKE_LOG_REL).read_text(encoding='utf-8').splitlines()]
                wakes = [row for row in rows if row.get('kind') in (None, 'wake')]
                self.assertEqual(wakes[-1]['unit'], key)
                # 工作台契约：唤醒只带**持久任务 ID**，意见正文去 store 里读（不再往唤醒语里塞全文）
                self.assertIn(task['task_id'], wakes[-1]['text'], '唤醒要带上持久任务 ID')
                self.assertNotIn('顺便把副标题删掉', wakes[-1]['text'],
                                 '意见正文不进唤醒语：读任务，不读对话')

                # ④ 页面手上还有**没落盘的直改**时，宿主前进一版 → 冲突；
                # 这一状态下提交意见必须被拒（不许拿旧基版去写），人写的字全留着。
                page.wait_for_function('() => saveQueues.size===0&&!draftPromise')
                page.locator('#svgStageWrap text').first.dblclick()
                page.locator('#inlineCanvasEditor').fill('人手上还没存上的字')
                page.evaluate("() => {clearTimeout(saveTimer);endInlineTextEdit(true)}")
                page.locator('#feedback').fill('再补一句意见')
                page.evaluate("() => { document.querySelector('#message').textContent = '' }")
                head = workbench_store.ensure(root)
                identity = next(node.get('data-workbench-id')
                                for node in ET.fromstring(workbench_store.get_page(root, key)['svg']).iter()
                                if node.tag.split('}')[-1] == 'text')
                advanced = workbench_store.commit(root, {
                    'op': 'save', 'operation_id': 'model_ahead', 'page_key': key,
                    'base_revision': head['pages'][key]['revision'], 'author': 'human',
                    'edits': [{'element_id': identity, 'kind': 'text', 'value': '模型重出的标题'}]},
                    browser=True)
                self.assertTrue(advanced.get('ok'), advanced)
                page.evaluate('() => onHostChanged()')
                page.wait_for_function("(k) => state[k].save_status==='conflict'", arg=key)
                self.assertFalse(page.locator('#staleNote').is_hidden(), '冲突要说给用户听')

                task_count = len(workbench_store.ensure(root)['tasks'])
                page.evaluate("() => dispatchFeedback('page')")
                page.wait_for_timeout(300)
                self.assertEqual(len(workbench_store.ensure(root)['tasks']), task_count,
                                 '陈旧页面不得再写进任务')
                self.assertEqual(page.evaluate('(k) => state[k].feedback', key), '再补一句意见',
                                 '被拒时人的字不许丢')
                self.assertEqual(page.evaluate('(k) => state[k].svg_edits[0].text', key), '人手上还没存上的字',
                                 '被拒时人手上没落盘的直改也要留着')
                message = page.locator('#message').inner_text()
                self.assertTrue('意见还没能存上' in message or '任务未提交' in message,
                                '被拒要说出来，不能静默什么都不做：%r' % message)
                self.assertEqual(errors, [])
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_typing_feedback_does_not_rebuild_the_rail(self):
        """写反馈打字时，左边的缩略图不该被销毁重建（2026-10-05 真人反馈）。

        `#feedback` 的 oninput → `autoState()` 原本调 `drawRail()`：**每敲一个字**，整条轨道
        连同每一张缩略图的重新取回都重来一遍（插件模式下是每页一次桥往返 + 一个新 blob）。
        人在左边看到的就是缩略图一直在动。

        判据要能证伪：先给每个缩略图打上 `data-probe` 标记，再敲一个字 ——
        标记还在＝没重建（新行为）；标记全没了＝被重建了（旧行为）。
        同时确认状态确实更新了（活动页变成 `revise`），别把"什么都不做"当成修好。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            state = review_host.start_host(root / review_surface.SURFACE_REL); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.wait_for_function("() => document.querySelectorAll('#rail img').length > 0")
                marked = page.evaluate("""() => {
                  const imgs = [...document.querySelectorAll('#rail img')];
                  imgs.forEach((el, i) => { el.dataset.probe = String(i) });
                  // 顺便数一数这次输入到底写了几个轨道按钮的 className：只该有当前页那一个。
                  let writes = 0;
                  const desc = Object.getOwnPropertyDescriptor(Element.prototype, 'className');
                  Object.defineProperty(Element.prototype, 'className', {
                    configurable: true,
                    get() { return desc.get.call(this) },
                    set(v) { if (this.parentElement && this.parentElement.id === 'rail') writes += 1; desc.set.call(this, v) },
                  });
                  const box = document.querySelector('#feedback');
                  box.value = '写一句意见';
                  box.dispatchEvent(new Event('input', { bubbles: true }));
                  const out = {
                    marked: imgs.length,
                    survived: document.querySelectorAll('#rail img[data-probe]').length,
                    writes: writes,
                    active: document.querySelector('#rail button.active').className,
                    total: document.querySelectorAll('#rail button').length,
                    feedback: state.alpha.feedback,
                  };
                  Object.defineProperty(Element.prototype, 'className', desc);
                  return out;
                }""")
                self.assertGreater(marked['marked'], 0, '轨道里得先有缩略图，否则这条断言什么也没证')
                self.assertEqual(marked['total'], marked['marked'], '缩略图数量应与页数一致')
                self.assertEqual(marked['survived'], marked['marked'],
                                 '打字只该改状态，不该销毁重建缩略图（重建会让整条轨道一直在动）')
                # 2026-10-16：判据跟着当前实现收紧。旧 UI 里「打字 → 活动页类名变 revise」，
                # 所以当年写的是 `writes==1`；现在的 rail 类名只反映页面保存状态，
                # 打字改的是反馈草稿，**一个轨道按钮都不该被重写**（类名没变就别写）。
                self.assertEqual(marked['writes'], 0,
                                 '打字只该改状态：连当前页那一个轨道按钮都不该重写（类名没变）')
                self.assertIn('active', marked['active'], '活动页仍是当前页')
                self.assertEqual(marked['feedback'], '写一句意见',
                                 '状态确实更新了 —— 别把「什么都不做」当成修好')
                self.assertEqual(page.evaluate("() => draftPayload().pages.alpha.feedback"), '写一句意见',
                                 '输入要真的进草稿，不能只停在 DOM 里')
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_render_during_a_region_drag_keeps_the_gesture(self):
        """拖拽中途来一次 render（启动那次宿主同步、模型改了页面都会触发）不许把框选吞掉。

        清掉 `marking` 之后 pointerup 会落进「没框到东西」那一支：人拖出来的框凭空消失、
        批注框不出现。判据就是「框还在、批注框开了」。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            state = review_host.start_host(root / review_surface.SURFACE_REL); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.wait_for_function("typeof canCommand!=='undefined'&&canCommand&&recoveryReady")
                page.wait_for_selector('#rail button[data-key]')
                page.wait_for_timeout(1200)
                page.get_by_text('框选', exact=True).click()
                box = page.locator('#preview').bounding_box()
                page.mouse.move(box['x'] + box['width'] * .1, box['y'] + box['height'] * .1)
                page.mouse.down()
                page.mouse.move(box['x'] + box['width'] * .25, box['y'] + box['height'] * .25)
                # 手势没结束时页面被重画一次（宿主同步/页面集合变化都会走到这里）
                page.evaluate('() => render()')
                page.mouse.move(box['x'] + box['width'] * .4, box['y'] + box['height'] * .4)
                page.mouse.up()
                page.wait_for_timeout(200)
                self.assertFalse(page.locator('#regionDialog').is_hidden(),
                                 '拖拽中途的那次重画把框选吞了：批注框不出现')
                self.assertTrue(page.evaluate('() => !!rect'), '框选区域不该被丢掉')
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_reorder_thumbnails_and_edit_text_in_place(self):
        """缩略图排序与画布原地改字都必须写入草稿，且不依赖顶部输入框。"""
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            state = review_host.start_host(root / review_surface.SURFACE_REL); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.wait_for_selector('#svgStageWrap svg text')

                first = page.locator('#rail button[data-key="alpha"]')
                second = page.locator('#rail button[data-key="omega"]')
                first_box = first.bounding_box(); second_box = second.bounding_box()
                page.mouse.move(first_box['x'] + first_box['width'] / 2, first_box['y'] + first_box['height'] / 2)
                page.mouse.down()
                page.mouse.move(second_box['x'] + second_box['width'] / 2,
                                second_box['y'] + second_box['height'] * .85, steps=10)
                page.mouse.up()
                self.assertEqual(page.evaluate("() => [...document.querySelectorAll('#rail button')].map(b => b.dataset.key)"),
                                 ['omega', 'alpha'])

                text = page.locator('#svgStageWrap svg text').first
                text_box = text.bounding_box()
                page.mouse.dblclick(text_box['x'] + text_box['width'] / 2, text_box['y'] + text_box['height'] / 2)
                editor = page.locator('#inlineCanvasEditor')
                self.assertTrue(editor.is_visible(), '双击文字后必须在原地出现编辑框')
                editor.press('ControlOrMeta+A')
                editor.type('Edited in place')
                editor.press('Enter')
                self.assertFalse(editor.is_visible(), '回车后原地编辑框应收起')
                self.assertEqual(page.locator('#svgStageWrap svg text').first.text_content(), 'Edited in place')

                draft_path = root / review_surface.DRAFT_REL
                deadline = time.monotonic() + 5
                draft = {}
                while time.monotonic() < deadline:
                    try:
                        draft = read(draft_path)
                        if isinstance(draft, dict) and draft.get('page_order') == ['omega', 'alpha'] and draft['pages']['alpha']['svg_edits']:
                            break
                    except (FileNotFoundError, json.JSONDecodeError, KeyError):
                        pass
                    time.sleep(.05)
                self.assertEqual(draft.get('page_order'), ['omega', 'alpha'])
                self.assertTrue(draft['pages']['alpha']['svg_edits'])
                self.assertTrue(page.locator('#inlineTextInput').is_hidden(),
                                '顶部栏不应再承载主文字编辑输入框')
                browser.close()
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_switching_pages_does_not_refetch_every_thumbnail(self):
        """翻页不该把整套缩略图重新向宿主取一遍（同一条浪费，只是触发频率低些）。

        `render()` 每次都整条重建轨道，而重建就要给每个缩略图取一次 URL（插件模式下是每页
        一次桥往返 + 一个新 blob）。资源按「路径 + 版本」记住之后，第二遍应该一次都不问宿主；
        版本变了（模型重出这一页）自然还是会去取 —— 键里带版本，所以不会拿到旧图。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            state = review_host.start_host(root / review_surface.SURFACE_REL); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.wait_for_function("() => [...document.querySelectorAll('#rail img')].every(i => i.src)")
                page.wait_for_timeout(300)          # 首屏该取的都取完了
                counts = page.evaluate("""async () => {
                  let n = 0;
                  const original = review.asset.bind(review);
                  review.asset = (...a) => { n += 1; return original(...a) };
                  const buttons = [...document.querySelectorAll('#rail button')];
                  buttons[1].click();               // 翻到第 2 页 → render → drawRail
                  await new Promise(r => setTimeout(r, 500));
                  const away = n; n = 0;
                  buttons[0].click();               // 翻回第 1 页
                  await new Promise(r => setTimeout(r, 500));
                  return { away: away, back: n, pages: buttons.length };
                }""")
                self.assertGreaterEqual(counts['pages'], 2, '这条断言要至少两页才有意义')
                self.assertEqual(counts['away'], 0, '翻过去时缩略图与舞台图都该用记住的 URL，不再问宿主')
                self.assertEqual(counts['back'], 0, '翻回来时同样不该重新取')
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_reload_keeps_unsubmitted_work(self):
        """点「重新加载」不该丢东西：草稿自动落盘，刷新后读回来（2026-10-05 真人反馈）。

        以前「提交」是唯一的落盘路径，所以没提交的意见/框选/直改只活在内存里，刷新即丢。
        现在任何状态变化都排一次草稿（停手 0.8 秒写进 surface 声明的 draft 文件），
        「重新加载」先把最后一笔刷出去再刷新。

        判据分两层：**磁盘上真有那份草稿**（不是只在内存里），以及**刷新之后那句话还在**。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            state = review_host.start_host(root / review_surface.SURFACE_REL); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")

                page.evaluate("""() => {
                  const box = document.querySelector('#feedback');
                  box.value = '这句还没提交';
                  box.dispatchEvent(new Event('input', { bubbles: true }));
                }""")
                # 停手 0.8 秒后才会写；等一下再看磁盘
                page.wait_for_timeout(1400)
                draft = read(root / '_internal/05_review' / 'draft.json')
                self.assertEqual(draft['pages']['alpha']['feedback'], '这句还没提交',
                                 '没提交的意见必须自动落到 draft 文件里')

                # 点「刷新」：现在是**原地同步**（宿主把集合/页序/新版本推过来），不整页 reload。
                # 判据不变：草稿已经落盘，同步之后那句话还在原地。
                page.evaluate("() => { window.__beforeReload = true }")
                page.click('#reload')
                page.wait_for_timeout(1500)
                self.assertTrue(page.evaluate("() => window.__beforeReload === true"),
                                '原地同步不该把整页刷掉')
                self.assertEqual(page.input_value('#feedback'), '这句还没提交',
                                 '同步之后草稿要读回来，页面就是同步前的样子')
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_draft_direct_edits_follow_the_page_version(self):
        """草稿里的直改按**页版本**恢复：画面没变就恢复，模型重出过就丢掉。

        `svg_edits` 的定位是元素树路径（`0.1` 这种）。页面一旦重画，同一个路径指向的就是
        另一个元素 —— 自动套回去会改坏别的东西。所以只认版本对得上的那些。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            surface_path = root / review_surface.SURFACE_REL
            state = review_host.start_host(surface_path); hosts.append(state)
            draft_path = root / '_internal/05_review' / 'draft.json'
            snapshot = read(root / '_internal/05_review' / 'snapshot.json')

            def draft_for(version):
                return {'review_id': snapshot['review_id'], 'at': '2026-10-05T00:00:00Z',
                        'pages': {'alpha': {'decision': 'pending', 'feedback': '', 'annotations': [],
                                            'assets': [], 'version': version,
                                            'svg_edits': [{'review_id': '0.1', 'tag': 'text',
                                                           'text': '草稿里的直改'}]}}}

            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})

                # ① 版本对得上 → 恢复
                write(draft_path, draft_for(snapshot['versions']['alpha']))
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.wait_for_timeout(500)
                self.assertEqual(page.evaluate("() => state.alpha.svg_edits.length"), 1,
                                 '画面没变，草稿里的直改该恢复')

                # ② 版本对不上（模型重出过这一页）→ 丢掉
                write(draft_path, draft_for('一个已经不存在的版本'))
                page.reload()
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.wait_for_timeout(500)
                self.assertEqual(page.evaluate("() => state.alpha.svg_edits.length"), 0,
                                 '画面已经被模型重出过，旧直改必须丢掉（元素树路径已经指到别处）')
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_reload_guard_still_catches_surfaces_without_drafts(self):
        """面**没有**声明 draft 时（比如模板审阅面），弹窗那条兜底必须还在。

        草稿是"刷新不丢"的正路；这条路不通时，页面不能又变回静默丢弃 —— 它得先问人。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            surface_path = root / review_surface.SURFACE_REL
            doc = read(surface_path)
            doc.pop('draft', None)
            doc['capabilities'] = [c for c in doc.get('capabilities', []) if c != 'draft']
            write(surface_path, doc)
            state = review_host.start_host(surface_path); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.evaluate("""() => {
                  window.__survived = true;
                  const box = document.querySelector('#feedback');
                  box.value = '这句还没提交';
                  box.dispatchEvent(new Event('input', { bubbles: true }));
                }""")
                page.click('#reload')
                page.wait_for_timeout(600)
                self.assertTrue(page.evaluate("() => window.__survived === true"),
                                '没有草稿可存时，点「重新加载」不该直接把页面刷新掉')
                self.assertTrue(page.evaluate("() => document.querySelector('#reloadDialog').open"),
                                '该先弹出「会丢掉什么」的选择框')
                what = page.locator('#reloadWhat').inner_text()
                self.assertIn('alpha', what, '要说清是哪一页')
                self.assertIn('意见', what, '要说清丢的是什么')
                page.locator('#reloadDialog').get_by_text('返回', exact=True).click()
                self.assertEqual(page.input_value('#feedback'), '这句还没提交', '返回之后不该动任何东西')
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_thumbnails_are_fetched_again_once_the_bridge_is_up(self):
        """轨道建在握手之前，那时根本取不到图 —— 桥接上以后必须重建一次。

        `boot()` 是 `render()` 在前、`connectWithTimeout()` 在后：轨道第一批缩略图是在
        `review === null` 时建的，`assetFor` 只能给一个同源降级地址。无插件宿主下那个地址是对的，
        **插件模式下页面在 `/api/review.page?…` 上，它必然 404** —— 而且之后再没人重取，
        缩略图就整场是破的（2026-10-05 截图：左侧 11–16 页全是破图）。

        判据：用 `add_init_script` 在页面脚本之前埋一个钩子，在 `DOMContentLoaded` 时给
        **握手前那一批**缩略图打标记。桥接上以后这批标记必须已经不存在（重建过了）；
        没有修复时它们会原样留着 —— 那正是破图那一批。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            state = review_host.start_host(root / review_surface.SURFACE_REL); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.add_init_script("""
                  addEventListener('DOMContentLoaded', () => {
                    document.querySelectorAll('#rail img').forEach((el, i) => { el.dataset.preBridge = String(i) });
                    window.__preBridgeCount = document.querySelectorAll('#rail img[data-pre-bridge]').length;
                  });
                """)
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                page.wait_for_function("() => [...document.querySelectorAll('#rail img')].every(i => i.src)")
                page.wait_for_function("() => [...document.querySelectorAll('#rail img')].every(i => i.complete && i.naturalWidth > 0)")
                probe = page.evaluate("""() => ({
                  pre: window.__preBridgeCount || 0,
                  stale: document.querySelectorAll('#rail img[data-pre-bridge]').length,
                  now: document.querySelectorAll('#rail img').length,
                })""")
                self.assertGreater(probe['pre'], 0, '握手前确实先建过一次轨道，否则这条断言没意义')
                self.assertEqual(probe['stale'], 0,
                                 '桥接上以后缩略图必须重新取一次，不能留着握手前那批取不到的')
                self.assertEqual(probe['now'], probe['pre'], '页数没变，缩略图数量也不该变')
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

    def test_reload_keeps_you_on_the_same_page(self):
        """点「重新加载」之后要停在原来那一页，不是被弹回第 1 页（2026-10-05 真人反馈）。

        当前页存在**地址的 hash** 上（`#<page_key>`），不用 `localStorage` —— 插件的不透明
        iframe 里读存储会直接抛，而且那个源每次加载都是新的，存了也读不回来。hash 随刷新一起保留。

        顺带把 hash 的**双向性**钉住：切页会写 hash，改 hash 也会切页 —— 它是"当前是哪一页"的
        唯一来源，不是一份悄悄同步的副本。
        """
        fixture = fixtures.V5Tests(); fixture.setUp(); root = fixture.root.resolve()
        hosts = []
        try:
            fixture.payload()
            state = review_host.start_host(root / review_surface.SURFACE_REL); hosts.append(state)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.goto(state['url'])
                page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
                self.assertIn('1 / 2', page.locator('#title').inner_text(), '打开时应在第 1 页')

                # 切到第 2 页：hash 要跟着变
                page.get_by_text('下一页', exact=True).click()
                page.wait_for_function("document.querySelector('#title').textContent.startsWith('2 /')")
                self.assertEqual(page.evaluate("() => decodeURIComponent(location.hash)"), '#omega',
                                 '切页要把当前页写进 hash')

                # 重新加载：还该停在原来那一页
                page.reload()
                page.wait_for_function("document.querySelector('#title').textContent.includes('/')")
                self.assertIn('2 / 2', page.locator('#title').inner_text(),
                              '重新加载之后应停在原来那一页，而不是弹回第 1 页')

                # 反向：改 hash 也要切页（它是唯一来源，不是副本）
                page.evaluate("() => { location.hash = 'alpha' }")
                page.wait_for_function("document.querySelector('#title').textContent.startsWith('1 /')")
        finally:
            for item in hosts: review_host.stop_host(item)
            fixture.tearDown()

if __name__ == '__main__':
    unittest.main()
