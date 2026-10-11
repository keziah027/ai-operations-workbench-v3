"""读取公开主页当前已展示的笔记；可复用用户自行登录的浏览器。"""
from datetime import datetime
import re
from urllib.parse import urlsplit

ALLOWED_HOSTS = {"www.xiaohongshu.com", "xiaohongshu.com", "xhslink.cn", "www.xhslink.cn", "xhslink.com", "www.xhslink.com"}


class AccountReadError(ValueError):
    pass


class AccountAccessError(AccountReadError):
    """登录或验证阻止访问；批量读取必须停止。"""


def check_page_access(page):
    body = page.locator("body").inner_text(timeout=5000)
    if "/website-login/error" in page.url or any(word in body for word in ["访问频繁", "访问异常", "安全验证", "网络环境存在风险", "IP存在风险"]):
        raise AccountAccessError("小红书要求验证或限制访问，请在小红书窗口中处理后再主动读取。")
    dialogs = page.locator('[role="dialog"], .login-container, .login-modal').filter(has_text="登录")
    if any(dialogs.nth(index).is_visible() for index in range(dialogs.count())):
        raise AccountAccessError("小红书要求登录后查看，请在小红书窗口中完成登录。")


def validate_profile_url(text):
    match = re.search(r"https://[^\s<>\"'，。]+", text.strip())
    if not match:
        raise AccountReadError("请粘贴小红书账号主页的 https 链接，也支持带链接的分享文字。")
    url = match.group(0)
    parts = urlsplit(url)
    try:
        valid_port = parts.port in (None, 443)
    except ValueError:
        valid_port = False
    if parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password or not valid_port:
        raise AccountReadError("仅支持小红书官方主页链接或 xhslink.cn / xhslink.com 分享链接。")
    if parts.hostname.endswith("xiaohongshu.com") and not re.fullmatch(r"/user/profile/[a-fA-F0-9]{24}/?", parts.path):
        raise AccountReadError("请提供账号主页链接，不是单篇笔记链接。")
    return url


def exact_count(text):
    """公开页面的 1千+ / 1.2万是模糊展示，不伪装成精确计数。"""
    from note_schema import count_info
    return count_info(text)['exact']


def parse_visible_cards(cards):
    result = []
    seen = set()
    for card in cards:
        identity = card.get("href")
        title = str(card.get("title") or "").strip()
        if not title or (identity and identity in seen):
            continue
        if identity:
            seen.add(identity)
        like_text = str(card.get("likes") or "").strip()
        result.append({"标题": title, "点赞": exact_count(like_text), "收藏": None, "评论": None,
                       "封面链接": str(card.get("cover") or ""),
                       "前台点赞显示": like_text or "未显示", "笔记链接": card.get("href") or "",
                       "数据状态": "未读取详情，当前仅有主页数据"})
    return result


def read_profile_page(page, text, limit=30):
    """在给定页面中读取；调用方负责浏览器生命周期与登录状态。"""
    from playwright.sync_api import TimeoutError as BrowserTimeout

    url = validate_profile_url(text)

    def restrict_navigation(route):
        request = route.request
        if request.is_navigation_request() and request.frame == page.main_frame:
            parts = urlsplit(request.url)
            if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
                route.abort()
                return
        route.fallback()

    def check_restrictions():
        check_page_access(page)

    page.route("**/*", restrict_navigation)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(1500)
        check_restrictions()
        parts = urlsplit(page.url)
        if parts.hostname not in {"www.xiaohongshu.com", "xiaohongshu.com"} or not re.fullmatch(r"/user/profile/[a-fA-F0-9]{24}/?", parts.path):
            raise AccountReadError("分享链接没有打开账号主页，可能需要登录或链接失效。请在小红书窗口中确认后复制完整主页链接。")
        try:
            page.locator("section.note-item").first.wait_for(state="visible", timeout=10000)
        except BrowserTimeout as exc:
            check_restrictions()
            raise AccountReadError("未找到可见笔记：账号可能无公开笔记、需要登录，或页面结构已变化。没有把这种情况当作 0 篇。") from exc
        check_restrictions()
        cards = page.locator("section.note-item").evaluate_all("""(elements, limit) => elements.slice(0, limit).map(el => {
            const title = el.querySelector('.title');
            const likes = el.querySelector('.like-wrapper .count');
            const link = el.querySelector('a.cover[href]') || el.querySelector('a[href]');
            const image = el.querySelector('a.cover img');
            return { title: title?.textContent?.trim() || '', likes: likes?.textContent?.trim() || '', href: link?.href || '', cover: image?.currentSrc || image?.src || '' };
        })""", limit)
        check_restrictions()
        notes = parse_visible_cards(cards)
        if not notes:
            raise AccountReadError("页面没有返回可识别的笔记标题，未生成统计。可能需要登录或更新页面适配。")
        interaction = page.locator(".user-interactions")
        return {"name": page.title().removesuffix(" - 小红书").strip(), "url": page.url,
                "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "profile_text": interaction.first.inner_text() if interaction.count() else "主页账号指标未能识别",
                "bio": page.locator('.user-desc').first.inner_text() if page.locator('.user-desc').count() else "",
                "notes": notes}
    except AccountReadError:
        raise
    except Exception as exc:
        raise AccountReadError("本次读取未完成，请检查小红书窗口是否仍打开、网络是否正常。未保存部分结果。") from exc
    finally:
        if not page.is_closed():
            page.unroute("**/*", restrict_navigation)


def collect_public_profile(text):
    url = validate_profile_url(text)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AccountReadError("账号读取组件尚未安装，请关闭运行窗口并双击 install.cmd 完成更新。") from exc
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            raise AccountReadError("本机缺少账号读取所需的浏览器组件，请双击 install.cmd 安装后重试。") from exc
        try:
            return read_profile_page(browser.new_page(), url)
        finally:
            browser.close()
