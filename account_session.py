"""单独的本机小红书浏览器。浏览器操作集中在同一线程，跨页面刷新复用。"""
import atexit
from concurrent.futures import Future, TimeoutError
from pathlib import Path
from queue import Queue, Empty
import shutil
from threading import Thread, Lock, Event
from uuid import uuid4

from account_reader import AccountReadError, read_profile_page, validate_profile_url

PROJECT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = PROJECT_DIR / ".local" / "xhs-browser"


def remove_profile(profile_dir):
    """只删除项目专用登录目录；拒绝目录链接或越界路径。"""
    expected = PROJECT_DIR / ".local" / "xhs-browser"
    if profile_dir != expected or profile_dir.resolve() != expected or profile_dir.is_symlink() or getattr(profile_dir, "is_junction", lambda: False)():
        raise AccountReadError("登录目录路径异常，已停止清理。")
    if profile_dir.exists():
        shutil.rmtree(profile_dir)


class AccountBrowser:
    def __init__(self):
        self._queue = Queue()
        self._call_lock = Lock()
        self._context = None
        self._page = None
        self._engine = None
        self._closed = False
        self._job_lock = Lock()
        self._job = None
        self._cancel = Event()
        self._active_future = None
        self._thread = Thread(target=self._run, name="xhs-browser", daemon=True)
        self._thread.start()
        atexit.register(self.shutdown)

    def _submit(self, action, value=None):
        if self._closed or not self._thread.is_alive():
            raise AccountReadError("登录窗口服务已关闭，请重新启动分析台。")
        if not self._call_lock.acquire(blocking=False):
            raise AccountReadError("浏览器正在处理上一次操作，请等待完成后再试。")
        try:
            if self._active_future is not None and not self._active_future.done():
                raise AccountReadError("正在读取笔记，请先点击停止并等待结束，再操作登录窗口。")
            future = Future()
            self._queue.put((action, value, future))
            try:
                return future.result(timeout=60)
            except TimeoutError as exc:
                future.cancel()
                raise AccountReadError("浏览器操作超时，请查看小红书窗口。未生成本次统计。") from exc
        finally:
            self._call_lock.release()

    def open_login(self):
        return self._submit("login")

    def open_creator(self):
        return self._submit("creator_login")

    def creator_status(self):
        return self._submit("creator_status")

    def read(self, url):
        return self._submit("read", validate_profile_url(url))

    def start_read(self, url, limit=100, include_details=True, use_login=True):
        url = validate_profile_url(url)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise AccountReadError("读取上限应为 1 到 1000 篇。")
        return self._start_job("batch", url, {"url": url, "limit": limit,
                                            "include_details": include_details, "use_login": use_login})

    def start_creator_read(self, days=7, limit=100):
        if days not in (7, 30) or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise AccountReadError("请选择近 7 日或近 30 日，笔记上限为 1～1000。")
        return self._start_job("creator_batch", "创作平台", {"days": days, "limit": limit})

    def _start_job(self, action, label, options):
        if not self._call_lock.acquire(blocking=False):
            raise AccountReadError("浏览器正在处理上一次操作，请稍后再试。")
        try:
            if self._closed or not self._thread.is_alive():
                raise AccountReadError("浏览器服务已关闭，请重启分析台。")
            if self._active_future is not None and not self._active_future.done():
                raise AccountReadError("已有读取任务正在进行，请先停止或等待完成。")
            identifier = uuid4().hex
            self._cancel = Event()
            with self._job_lock:
                self._job = {"id": identifier, "status": "running", "input": label,
                             "kind": "creator" if action == "creator_batch" else "public",
                             "stage": "准备", "loaded": 0, "processed": 0, "requested": options["limit"],
                             "message": "正在准备浏览器", "result": None, "error": None}
            future = Future()
            self._active_future = future
            self._queue.put((action, options, future))
            return identifier
        finally:
            self._call_lock.release()

    def job_status(self):
        with self._job_lock:
            return dict(self._job) if self._job else None

    def cancel_read(self, identifier):
        with self._job_lock:
            if self._job and self._job["id"] == identifier and self._job["status"] == "running":
                self._cancel.set()
                self._job["message"] = "正在停止，会保留已经确认的数据；等待当前页面操作结束"

    def _progress(self, **state):
        with self._job_lock:
            if self._job:
                self._job.update(state)

    def close(self):
        return self._submit("close")

    def clear_login(self):
        return self._submit("clear")

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self._cancel.set()
        self._queue.put(("stop", None, Future()))
        self._thread.join(timeout=5)

    def _ensure_context(self):
        if self._context is not None and self._context.pages:
            return
        self._context = None
        self._page = None
        if self._engine is None:
            from playwright.sync_api import sync_playwright
            self._engine = sync_playwright().start()
        if PROFILE_DIR.resolve() != PROFILE_DIR:
            raise AccountReadError("登录目录路径异常，请检查项目文件夹。")
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self._context = self._engine.chromium.launch_persistent_context(
                str(PROFILE_DIR), headless=False, accept_downloads=False)
        except Exception as exc:
            raise AccountReadError("无法打开登录窗口。请确认没有另一份分析台占用该窗口；若缺少组件，请运行 install.cmd。") from exc
        self._context.on("close", self._on_closed)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    def _on_closed(self, *_):
        self._context = None
        self._page = None

    def _close_context(self):
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass  # 用户可能已经手动关闭了整个浏览器。
        finally:
            self._on_closed()

    def _execute(self, action, value):
        if action in ("close", "clear"):
            self._close_context()
            if action == "clear":
                remove_profile(PROFILE_DIR)
            return
        if action == "batch":
            from account_batch import read_account_batch
            options = dict(limit=value["limit"], include_details=value["include_details"],
                           cancelled=self._cancel.is_set, progress=self._progress)
            if not value["use_login"]:
                from playwright.sync_api import sync_playwright
                if self._engine is None:
                    self._engine = sync_playwright().start()
                browser = self._engine.chromium.launch(headless=True)
                try:
                    return read_account_batch(browser.new_page(), value["url"], **options)
                finally:
                    browser.close()
            self._ensure_context()
            if self._page is None or self._page.is_closed():
                self._page = self._context.new_page()
            return read_account_batch(self._page, value["url"], **options)
        self._ensure_context()
        if action in ("creator_login", "creator_status", "creator_batch"):
            from urllib.parse import urlsplit
            creator_tabs = [tab for tab in self._context.pages
                            if urlsplit(tab.url).hostname == "creator.xiaohongshu.com"]
            creator = next((tab for tab in creator_tabs if urlsplit(tab.url).path == "/statistics/data-analysis"),
                           creator_tabs[0] if creator_tabs else None)
            if creator is None:
                creator = self._context.new_page()
                creator.goto("https://creator.xiaohongshu.com/", wait_until="domcontentloaded", timeout=25000)
                creator.wait_for_timeout(1500)
            creator.bring_to_front()
            if action == "creator_login":
                return
            if action == "creator_batch":
                from creator_reader import read_creator_dashboard
                return read_creator_dashboard(creator, days=value["days"], limit=value["limit"],
                                              cancelled=self._cancel.is_set, progress=self._progress)
            from creator_reader import check_creator_login
            return check_creator_login(creator)
        if self._page is None or self._page.is_closed():
            self._page = self._context.new_page()
        if action == "login":
            self._page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=25000)
            self._page.bring_to_front()
            return
        if action == "read":
            self._page.bring_to_front()
            # 不创建无登录的新浏览器；始终复用用户自行登录的同一上下文。
            return read_profile_page(self._page, value)
        raise AccountReadError("无法识别浏览器操作。")

    def _run(self):
        try:
            while True:
                try:
                    action, value, future = self._queue.get(timeout=0.15)
                except Empty:
                    # 让可见浏览器继续处理扫码、输入、导航和关闭事件。
                    if self._context is not None and self._context.pages:
                        try:
                            self._context.pages[0].wait_for_timeout(100)
                        except Exception:
                            self._close_context()
                    continue
                if action == "stop":
                    break
                if future.cancelled():
                    continue
                try:
                    result = self._execute(action, value)
                except Exception as exc:
                    error = exc if isinstance(exc, AccountReadError) else AccountReadError("浏览器操作未完成，请检查窗口或重新打开登录入口。")
                    if not future.cancelled():
                        future.set_exception(error)
                    if action in ("batch", "creator_batch"):
                        self._progress(status="error", error=str(error))
                else:
                    if not future.cancelled():
                        future.set_result(result)
                    if action in ("batch", "creator_batch"):
                        self._progress(status="done", result=result)
        finally:
            self._close_context()
            if self._engine is not None:
                self._engine.stop()
