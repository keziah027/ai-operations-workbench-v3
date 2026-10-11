"""按用户选择的上限加载主页，并在同一登录浏览器中逐篇读取详情。"""
from datetime import datetime
import re
import time
from urllib.parse import urlsplit

from account_reader import (AccountReadError, AccountAccessError, ALLOWED_HOSTS,
                            check_page_access, exact_count, parse_visible_cards, read_profile_page)


def note_identity(url):
    # 去除签名参数后再去重，避免置顶笔记或不同来源参数被重复统计。
    parts = urlsplit(url)
    tail = parts.path.rstrip("/").split("/")[-1]
    return (tail if re.fullmatch(r"[a-fA-F0-9]{24}", tail) else parts.path.rstrip("/")) if url else None


def valid_note_url(url):
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.hostname in {"www.xiaohongshu.com", "xiaohongshu.com"}
            and not parts.username and not parts.password and parts.port in (None, 443)
            and bool(re.fullmatch(r"/(?:explore|discovery/item)/[a-fA-F0-9]{24}/?|/user/profile/[a-fA-F0-9]{24}/[a-fA-F0-9]{24}/?", parts.path)))


def merge_notes(current, added, limit):
    seen = {note_identity(note["笔记链接"]) for note in current if note["笔记链接"]}
    for note in added:
        identity = note_identity(note["笔记链接"])
        if len(current) >= limit:
            break
        if identity and identity not in seen:
            current.append(note)
            seen.add(identity)


def collect_cards(page):
    return parse_visible_cards(page.locator("section.note-item").evaluate_all("""elements => elements.map(el => {
        const title = el.querySelector('.title');
        const link = el.querySelector('a.cover[href]') || el.querySelector('a[href]');
        return {title: title?.textContent?.trim() || '',
                likes: el.querySelector('.like-wrapper .count')?.textContent?.trim() || '', href: link?.href || '',
                cover: el.querySelector('a.cover img')?.currentSrc || el.querySelector('a.cover img')?.src || ''};
    })"""))


def read_note_detail(page, note):
    """只读取笔记互动栏，不点击点赞/收藏按钮，也不读取评论用户信息。"""
    url = note["笔记链接"]
    if not valid_note_url(url):
        raise AccountReadError("无法识别笔记链接")
    page.goto(url, wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(1000)
    check_page_access(page)
    try:
        page.locator("#noteContainer .interact-container").wait_for(state="visible", timeout=8000)
    except Exception as exc:
        check_page_access(page)
        raise AccountReadError("笔记已删除、不可见或详情未加载") from exc
    # 所有指标限定在这篇笔记的互动栏，避免误取评论点赞或背景列表数据。
    bar = page.locator("#noteContainer .interact-container").first
    raw = {}
    for metric, selector in [("点赞", ".like-wrapper .count"), ("收藏", ".collect-wrapper .count"), ("评论", ".chat-wrapper .count")]:
        count = bar.locator(selector)
        raw[metric] = count.first.inner_text().strip() if count.count() and count.first.is_visible() else ""
    check_page_access(page)
    # 页面最终笔记标识必须与请求一致，防止跳转后把别篇数据写进来。
    final_id = urlsplit(page.url).path.rstrip("/").split("/")[-1]
    expected_id = urlsplit(url).path.rstrip("/").split("/")[-1]
    if final_id != expected_id:
        raise AccountReadError("详情页跳转到其他笔记，未采用数据")
    update = {f"前台{metric}显示": value or "未显示" for metric, value in raw.items()}
    for metric, value in raw.items():
        number = exact_count(value)
        if metric != "点赞" or number is not None:
            update[metric] = number
    update["详情读取时间"] = datetime.now().astimezone().isoformat(timespec="seconds")
    # 只采集作者正文区，避免把评论、推荐笔记或页面导航当成作者内容。
    desc = page.locator("#noteContainer #detail-desc")
    update["正文"] = desc.first.inner_text().strip() if desc.count() else ""
    update["正文读取状态"] = "已读取作者正文" if update["正文"] else "未找到可读作者正文"
    update["正文话题"] = "、".join(desc.first.locator("a.tag").all_text_contents()) if desc.count() else ""
    product_links = page.locator("#noteContainer .note-content a[href]").evaluate_all("""els => els.map(e=>({text:e.innerText.trim(),url:e.href}))
        .filter(e=>e.text && /商品|购买|店铺|橱窗/.test(e.text))""")
    update["可见商品入口"] = product_links
    update["数据状态"] = "详情已读取" if all(exact_count(value) is not None for value in raw.values()) else "详情已读取，部分数字未确认"
    note.update(update)


def read_account_batch(page, text, limit=100, include_details=True, cancelled=None, progress=None):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise AccountReadError("读取上限应为 1 到 1000 篇。")
    cancelled = cancelled or (lambda: False)
    progress = progress or (lambda **state: None)
    deadline = time.monotonic() + 1800

    def stopped():
        return cancelled() or time.monotonic() > deadline

    def pause(milliseconds):
        for _ in range(max(1, milliseconds // 200)):
            if stopped():
                return
            page.wait_for_timeout(200)

    progress(stage="主页", loaded=0, processed=0, requested=limit, message="正在打开账号主页")
    result = read_profile_page(page, text, limit=limit)
    notes = []
    merge_notes(notes, result["notes"], limit)
    if not notes:
        raise AccountReadError("未能识别可用笔记链接，未将此情况计为 0 篇。")
    result["notes"] = notes
    reason = "达到设定读取上限"
    warnings = []
    stalled = 0
    detail_page = None
    restricted = False
    processed = succeeded = 0
    try:
        for _ in range(max(20, limit * 2)):
            progress(stage="主页", loaded=len(notes), processed=0, requested=limit, message=f"已找到 {len(notes)} 篇，正在向下加载")
            if stopped() or len(notes) >= limit:
                break
            check_page_access(page)
            before = len(notes)
            last = page.locator("section.note-item").last
            if last.count():
                last.scroll_into_view_if_needed(timeout=4000)
            page.mouse.wheel(0, 1800)
            pause(1600)
            check_page_access(page)
            merge_notes(notes, collect_cards(page), limit)
            stalled = stalled + 1 if len(notes) == before else 0
            if stalled >= 3:
                reason = "连续 3 次滚动未出现新笔记，不能保证已覆盖全部历史"
                break
        else:
            reason = "达到本次滚动次数上限"
        if stopped():
            reason = "用户停止读取" if cancelled() else "达到本次 30 分钟时间上限"
        if include_details and not stopped():
            detail_page = page.context.new_page()

            def navigation_guard(route):
                request = route.request
                if request.is_navigation_request() and request.frame == detail_page.main_frame:
                    parts = urlsplit(request.url)
                    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
                        route.abort()
                        return
                route.fallback()
            detail_page.route("**/*", navigation_guard)
            failures = 0
            for note in notes:
                if stopped():
                    reason = "用户停止读取" if cancelled() else "达到本次 30 分钟时间上限"
                    break
                progress(stage="详情", loaded=len(notes), processed=processed, requested=limit,
                         message=f"正在读取第 {processed + 1}/{len(notes)} 篇的收藏和评论")
                try:
                    read_note_detail(detail_page, note)
                    succeeded += 1
                    failures = 0
                except AccountAccessError:
                    note["数据状态"] = "详情遇到登录或访问限制，未读取"
                    raise
                except Exception:
                    note["数据状态"] = "详情无法读取，保留已确认数据"
                    failures += 1
                processed += 1
                if failures >= 3:
                    reason = "连续 3 篇详情无法读取，已停止；其余笔记仍保留主页数据"
                    break
                pause(1000)
    except AccountAccessError as exc:
        restricted = True
        reason = "遇到平台登录、验证或访问限制，读取已停止"
        warnings.append(str(exc))
    except Exception:
        reason = "页面或网络中断，已保留此前确认的数据"
    finally:
        if detail_page is not None and not restricted:
            try:
                detail_page.close()
            except Exception:
                pass
    result.update(requested_limit=limit, include_details=include_details, processed_details=processed,
                  successful_details=succeeded, stop_reason=reason, warnings=warnings,
                  completed_at=datetime.now().astimezone().isoformat(timespec="seconds"), full_account=False)
    progress(stage="完成", loaded=len(notes), processed=processed, requested=limit, message=reason)
    from note_schema import normalize_notes
    result['notes'] = normalize_notes(result['notes'])
    return result
