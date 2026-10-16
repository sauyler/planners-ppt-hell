"""2026-10-16 侧栏工作台真人反馈的四个 Bug —— 复现回路（诊断用，先红后绿）。

症状 → 用例：
  ① 点「下一页」时左侧缩略图条自动上移     → test_next_page_keeps_the_rail_scroll
  ② 提交整套反馈后没有通知（静默失败）     → test_batch_submit_never_fails_silently
  ③ 页序未保存 / 同步未完成（冲突死锁）    → test_reload_resyncs_when_pending_work_conflicts
  ④ 页面增删没有起效                       → test_reload_picks_up_pages_added_or_deleted

跑法：PPT_BROWSER_TESTS=1 python3 -m unittest test.test_review_reported_bugs -v
"""
import json
import os
import sys
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_v5 as fixtures  # noqa: E402
from project_state import CONTENT, sync, write  # noqa: E402
import review_surface  # noqa: E402
import workbench_store  # noqa: E402
from lib.planners_modules import resolve_module  # noqa: E402

sys.path.insert(0, str(resolve_module('planners-review-core') / 'scripts' / 'lib'))
import review_host  # noqa: E402

HEAD_REL = Path('_internal/06_workbench/head.json')
PAGE_COUNT = 10  # 缩略图必须真的能滚起来，两个页面测不出「自动上移」


def head(root):
    path = root / HEAD_REL
    for _ in range(200):
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(.05)
    raise AssertionError('workbench head.json 一直读不到')


def op_id(name):
    return name + '_' + uuid.uuid4().hex[:10]


@unittest.skipUnless(os.environ.get('PPT_BROWSER_TESTS') == '1',
                     'set PPT_BROWSER_TESTS=1 for local browser/interface smoke')
class ReportedBugTests(unittest.TestCase):
    def build(self, count=PAGE_COUNT):
        """一个够长的假项目：缩略图条会溢出，能滚。"""
        fixture = fixtures.V5Tests()
        fixture.setUp()
        root = fixture.root.resolve()
        keys = ['p%02d' % (i + 1) for i in range(count)]
        write(root / CONTENT, {'project': 'Test', 'pages': [
            {'page_key': k, 'title': k, 'content': '42% with qualification', 'source_assets': []}
            for k in keys]})
        sync(root)
        for k in keys:
            fixture.svg(k)
        fixture.seal()
        fixture.payload()
        return fixture, root, keys

    def open_surface(self, root):
        host = review_host.start_host(root / review_surface.SURFACE_REL)
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.goto(host['url'])
        page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
        page.wait_for_selector('#rail button[data-key]')
        return pw, browser, page, host

    # ── ① 缩略图自动上移 ───────────────────────────────────────────────
    def test_next_page_keeps_the_rail_scroll(self):
        fixture, root, keys = self.build()
        pw = browser = host = None
        try:
            pw, browser, page, host = self.open_surface(root)
            page.wait_for_timeout(400)
            assert page.evaluate("() => document.querySelector('#rail').scrollHeight > document.querySelector('#rail').clientHeight"), \
                '夹具坏了：缩略图条没有溢出，滚不动就测不出上移'
            page.evaluate("() => { document.querySelector('#rail').scrollTop = 260 }")
            time.sleep(.2)
            before = page.evaluate("() => document.querySelector('#rail').scrollTop")
            self.assertGreater(before, 100, '前置条件：轨道已经滚下去了')

            page.click('#pageNext')
            page.wait_for_timeout(400)
            after = page.evaluate("() => document.querySelector('#rail').scrollTop")
            self.assertLessEqual(
                abs(after - before), 4,
                '点「下一页」后缩略图条被拉回顶部（%d → %d）：翻页不该动轨道的滚动位置' % (before, after))
        finally:
            if browser:
                browser.close()
            if pw:
                pw.stop()
            if host:
                review_host.stop_host(host)
            fixture.tearDown()

    # ── ② 整套提交静默失败 ─────────────────────────────────────────────
    def test_batch_submit_still_lands_a_task_and_a_wake(self):
        """症状②：整套提交之后既没落任务、也没有唤醒 —— 人以为提了，模型收不到。

        侧栏是插件宿主（postMessage），所以这里把 transport 换成 postMessage 并记录 wake，
        与真人环境一致；唤醒就是「通知」。
        """
        fixture, root, keys = self.build()
        pw = browser = host = None
        try:
            pw, browser, page, host = self.open_surface(root)
            page.wait_for_timeout(400)
            page.evaluate("""() => {
              window.__wakes = [];
              review = Object.assign({}, review, {transport: 'postMessage',
                wake: async (m) => { window.__wakes.push(m) }});
            }""")
            # 宿主那边把顺序换掉 → 页面手上的 base_order 永远是旧的
            h = head(root)
            swapped = list(h['order'])
            swapped[0], swapped[1] = swapped[1], swapped[0]
            workbench_store.commit(root, {'op': 'order', 'operation_id': op_id('behind'),
                                          'order': swapped, 'base_order': h['order']})
            # 页面上再攒一条待保存的顺序修改，逼 flushWorkbench 走进冲突
            page.evaluate("() => reorderPages('%s', '%s', true)" % (keys[2], keys[0]))
            before_tasks = set(head(root).get('tasks', {}))

            page.click('#deckDispatch')
            page.wait_for_selector('#submitDialog[open]')
            page.fill('#overall', '整套都要再收紧一点')
            page.click('#submitBatchBtn')
            page.wait_for_timeout(2000)

            submitted = set(head(root).get('tasks', {})) - before_tasks
            wakes = page.evaluate("() => window.__wakes")
            message = page.locator('#message').inner_text().strip()
            self.assertTrue(
                submitted,
                '整套提交没有落到任何持久任务上（提示："%s"，唤醒 %d 次）：模型那边永远收不到'
                % (message, len(wakes)))
            self.assertTrue(
                any('整套' in json.dumps(w, ensure_ascii=False) for w in wakes),
                '任务落了，但没有发出「整套」唤醒（wakes=%s）' % json.dumps(wakes, ensure_ascii=False))
        finally:
            if browser:
                browser.close()
            if pw:
                pw.stop()
            if host:
                review_host.stop_host(host)
            fixture.tearDown()

    # ── ③ 冲突把「同步」也一起锁死 ─────────────────────────────────────
    def test_reload_resyncs_when_pending_work_conflicts(self):
        """宿主已经变了 + 页面攒着待保存的顺序 → 「刷新」必须还能把人拉回一致状态。"""
        fixture, root, keys = self.build()
        pw = browser = host = None
        try:
            pw, browser, page, host = self.open_surface(root)
            page.wait_for_timeout(400)
            # 人先写一句意见（冲突之后必须还在）
            page.fill('#feedback', '这一页的结论要重写')
            # 模型那边删了一页 → 宿主的 order 变了
            h = head(root)
            victim = keys[-1]
            workbench_store.commit(root, {
                'op': 'delete_page', 'operation_id': op_id('behind_del'), 'page_key': victim,
                'base_order': h['order'], 'base_revision': h['pages'][victim]['revision']})
            # 页面手上的 order 也改过 → saveOrder 拿旧 base_order 必冲突
            page.evaluate("() => reorderPages('%s', '%s', false)" % (keys[0], keys[1]))

            page.click('#reload')
            page.wait_for_timeout(2500)

            rail = page.evaluate("() => [...document.querySelectorAll('#rail button')].map(b => b.dataset.key)")
            self.assertEqual(
                rail, head(root)['order'],
                '刷新之后轨道仍与宿主不一致（页面 %d 个 / 宿主 %d 个）：冲突一旦发生，人再也同步不回来'
                % (len(rail), len(head(root)['order'])))
            self.assertEqual(page.input_value('#feedback'), '这一页的结论要重写',
                             '同步不该丢掉人写的东西')
        finally:
            if browser:
                browser.close()
            if pw:
                pw.stop()
            if host:
                review_host.stop_host(host)
            fixture.tearDown()

    # ── ④ 增删没反映到页面上 ───────────────────────────────────────────
    def test_reload_picks_up_pages_added_or_deleted(self):
        """没有待保存工作时，刷新就应该看到宿主当前的页面集合。"""
        fixture, root, keys = self.build()
        pw = browser = host = None
        try:
            pw, browser, page, host = self.open_surface(root)
            page.wait_for_timeout(400)
            h = head(root)
            victim = keys[-1]
            workbench_store.commit(root, {
                'op': 'delete_page', 'operation_id': op_id('plain_del'), 'page_key': victim,
                'base_order': h['order'], 'base_revision': h['pages'][victim]['revision']})

            page.click('#reload')
            page.wait_for_timeout(2500)
            rail = page.evaluate("() => [...document.querySelectorAll('#rail button')].map(b => b.dataset.key)")
            self.assertNotIn(victim, rail, '被删掉的页还挂在缩略图条上')
            self.assertEqual(rail, head(root)['order'])
        finally:
            if browser:
                browser.close()
            if pw:
                pw.stop()
            if host:
                review_host.stop_host(host)
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
