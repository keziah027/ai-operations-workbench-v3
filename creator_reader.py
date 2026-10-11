"""创作平台只读适配：先核实后台登录，再读取已显示的数据。"""
from urllib.parse import urlsplit
from datetime import datetime
import re
import time

from account_reader import AccountAccessError, AccountReadError, exact_count

HOME_URL = "https://creator.xiaohongshu.com/new/home"
NOTES_URL = "https://creator.xiaohongshu.com/statistics/data-analysis"
OVERVIEW_METRICS = ["曝光数", "观看数", "封面点击率", "视频完播率", "点赞数", "评论数", "收藏数", "分享数", "净涨粉", "新增关注", "取消关注", "主页访客"]
NOTE_METRICS = ["曝光", "观看", "点赞", "评论", "收藏", "涨粉", "分享", "弹幕"]


def check_creator_login(page):
    parts = urlsplit(page.url)
    if parts.hostname != "creator.xiaohongshu.com":
        raise AccountReadError("当前窗口不是小红书创作服务平台，请重新打开入口。")
    body = page.locator("body").inner_text(timeout=5000)
    if any(word in body for word in ["访问频繁", "访问异常", "安全验证", "网络环境存在风险"]):
        raise AccountAccessError("创作平台要求验证或限制访问，请在专用窗口中处理后再检查。")
    if parts.path.rstrip("/") == "/login" or ("短信登录" in body and "发送验证码" in body):
        raise AccountAccessError("创作服务平台尚未登录。公开主页的登录不一定适用于创作平台，请在专用窗口中完成后台登录。")
    # 必须看到后台导航，不能把非登录页简单当作已登录。
    if not any(word in body for word in ["笔记管理", "数据中心", "数据看板"]):
        raise AccountReadError("后台页面尚未加载完整，暂时无法确认登录，请稍后再检查。")
    return {"url": page.url, "status": "已进入创作平台后台"}


def parse_overview(body):
    """仅解析笔记总览区，避免把最新笔记、推荐账号等数据混入。"""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    account = re.search(r"小红书账号[:：]\s*(\S+)", body)
    if not account or "笔记数据总览" not in lines or "最新笔记" not in lines:
        raise AccountReadError("无法确认创作平台账号或笔记总览，未生成账号统计。")
    block = lines[lines.index("笔记数据总览"):lines.index("最新笔记")]
    period = next((line for line in block if line.startswith("统计周期")), None)
    if not period:
        raise AccountReadError("无法确认账号总览的统计周期。")
    metrics = []
    for label in OVERVIEW_METRICS:
        if label not in block:
            raise AccountReadError(f"后台总览缺少“{label}”，需要核对页面适配。")
        index = block.index(label)
        raw = block[index + 1] if index + 1 < len(block) else ""
        if not re.fullmatch(r"[-+]?\d[\d,.]*(?:万|亿|千|%|\+)?|--|—|-", raw):
            raise AccountReadError(f"无法确认“{label}”的数值，未采用可能错位的数据。")
        comparison = block[index + 2] if index + 2 < len(block) and block[index + 2].startswith("环比") else "未显示"
        metrics.append({"指标": label, "后台显示": raw, "环比": comparison})
    name = lines[1] if lines[0] == "创作服务平台" else "当前登录账号"
    return {"name": name, "account_id": account.group(1), "period": period, "metrics": metrics}


def parse_note_rows(headers, rows):
    required = {"笔记基础信息", "点赞", "收藏", "评论"}
    if not required.issubset(headers) or len(headers) != len(set(headers)):
        raise AccountReadError("后台笔记表头已变化，无法确认点赞、收藏、评论的列位置。")
    result = []
    for row in rows:
        if len(row["cells"]) != len(headers) or not row["title"]:
            raise AccountReadError("后台笔记行未加载完整，未采用错位的数据。")
        date = re.fullmatch(r"发布于(\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)", row["date"].strip())
        if not date:
            raise AccountReadError("无法确认笔记首次发布时间，未把其他日期用于统计。")
        values = dict(zip(headers, row["cells"]))
        note = {"标题": row["title"], "发布时间": date.group(1),
                '图文/视频':row.get('type') or values.get('内容形式') or values.get('笔记类型') or ''}
        for label in NOTE_METRICS:
            if label in values:
                note[label] = exact_count(values[label])
                note[f"后台{label}显示"] = values[label]
        for label in ["封面点击率", "人均观看时长"]:
            if label in values:
                note[label] = values[label]
        note["数据状态"] = "后台笔记表已读取" if all(note.get(label) is not None for label in ["点赞", "收藏", "评论"]) else "后台笔记表已读取，部分互动数未确认"
        from note_schema import normalize_note
        result.append(normalize_note(note))
    return result


def period_length(period):
    match = re.search(r"(\d{2}-\d{2})\s*至\s*(\d{2}-\d{2})", period)
    if not match:
        raise AccountReadError("无法确认账号总览的日期范围。")
    year = datetime.now().year
    start = datetime.strptime(f"{year}-{match.group(1)}", "%Y-%m-%d")
    end = datetime.strptime(f"{year}-{match.group(2)}", "%Y-%m-%d")
    if start > end:
        start = start.replace(year=year - 1)
    return (end - start).days + 1


def table_payload(page):
    table = page.locator("table").filter(has=page.locator("th[data-key='noteInfo']")).first
    return table.evaluate("""table => ({
        headers: [...table.querySelectorAll('thead th')].map(e=>e.innerText.trim()),
        rows: [...table.querySelectorAll('tbody tr')].filter(e=>e.querySelector('.note-title')).map(e=>({
            title:e.querySelector('.note-title').innerText.trim(),
            date:e.querySelector('.time')?.innerText.trim() || '',
            cells:[...e.querySelectorAll('td')].map(c=>c.innerText.trim())
        }))
    })""")


def note_filters(page):
    # 只读取已经核对的日期筛选控件，不采集其他输入内容。
    dates = page.locator("input.d-text").evaluate_all("els=>els.map(e=>e.value).filter(v=>/^\\d{4}-\\d{2}-\\d{2}$/.test(v))")
    if len(dates) != 2:
        raise AccountReadError("无法确认笔记首发时间筛选范围，请在后台内容分析中检查日期。")
    body = page.locator("body").inner_text()
    kind = re.search(r"笔记类型\s*\n([^\n]+)", body)
    return {"start": dates[0], "end": dates[1], "type": kind.group(1).strip() if kind else "未确认"}


def read_creator_dashboard(page, days=7, limit=100, cancelled=None, progress=None):
    if days not in (7, 30) or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise AccountReadError("请使用近 7 日或近 30 日，并将笔记上限设为 1～1000。")
    cancelled = cancelled or (lambda: False)
    progress = progress or (lambda **state: None)
    check_creator_login(page)
    deadline = time.monotonic() + 1800
    result = {"captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
              "overview": None, "notes": [], "filters": None, "platform_total": None,
              "requested_limit": limit, "warnings": [], "stop_reason": "读取完成",
              "source": NOTES_URL, "days": days, "complete_filtered": False}
    overview_page = None
    try:
        progress(stage="账号总览", loaded=0, processed=0, requested=limit, message=f"正在读取账号近 {days} 日数据")
        overview_page = page.context.new_page()
        overview_page.goto(HOME_URL, wait_until="domcontentloaded", timeout=25000)
        overview_page.get_by_text("笔记数据总览", exact=True).wait_for(timeout=15000)
        check_creator_login(overview_page)
        overview_page.get_by_text(f"近{days}日", exact=True).click(timeout=5000)
        overview_page.wait_for_timeout(1800)
        check_creator_login(overview_page)
        for _ in range(12):
            overview = parse_overview(overview_page.locator("body").inner_text())
            if period_length(overview["period"]) == days:
                result["overview"] = overview
                break
            overview_page.wait_for_timeout(500)
        else:
            raise AccountReadError("后台统计周期尚未切换完成，请稍后重新同步。")
        if cancelled():
            result["stop_reason"] = "用户停止读取，已保留账号总览"
            return result
        progress(stage="后台笔记", message="正在核对后台笔记表及日期筛选")
        if urlsplit(page.url).path != "/statistics/data-analysis":
            page.goto(NOTES_URL, wait_until="domcontentloaded", timeout=25000)
        page.locator("th[data-key='noteInfo']").wait_for(timeout=15000)
        page.wait_for_timeout(1200)
        check_creator_login(page)
        result["filters"] = note_filters(page)
        total_text = page.locator(".d-pagination-total").inner_text(timeout=5000)
        total_match = re.search(r"共\s*(\d+)\s*条", total_text)
        if not total_match:
            raise AccountReadError("无法确认后台笔记总条数，未将空白页面算成零篇。")
        total = result["platform_total"] = int(total_match.group(1))
        if total == 0:
            result.update(complete_filtered=True, stop_reason="当前筛选范围内无笔记")
            return result
        first = page.locator(".d-pagination-page-content").filter(has_text=re.compile(r"^1$"))
        if first.count() and "bold" not in (first.get_attribute("class") or ""):
            old_rows = table_payload(page)["rows"]
            previous = old_rows[0]["title"] + old_rows[0]["date"] if old_rows else ""
            first.click(timeout=5000)
            page.wait_for_function("old=>{const r=document.querySelector('table tbody tr');return r && (r.querySelector('.note-title')?.innerText.trim()+r.querySelector('.time')?.innerText.trim())!==old}", arg=previous, timeout=12000)
            page.wait_for_timeout(1200)
        seen_pages = set()
        for _ in range(100):
            if cancelled() or time.monotonic() > deadline:
                result["stop_reason"] = "用户停止读取" if cancelled() else "达到 30 分钟时间上限"
                break
            check_creator_login(page)
            if note_filters(page) != result["filters"]:
                raise AccountReadError("读取途中筛选条件发生变化，已停止以免混合不同范围的数据。")
            payload = table_payload(page)
            rows = parse_note_rows(payload["headers"], payload["rows"])
            signature = tuple((row["标题"], row["发布时间"]) for row in rows)
            if not rows or signature in seen_pages:
                raise AccountReadError("笔记页没有出现新内容，已停止以免重复统计。")
            seen_pages.add(signature)
            result["notes"].extend(rows[:max(0, limit - len(result["notes"]))])
            count = len(result["notes"])
            progress(stage="后台笔记", loaded=count, processed=count, requested=min(total, limit), message=f"已读取后台笔记 {count}/{min(total, limit)} 篇")
            if count >= total:
                result["complete_filtered"] = count == total
                result["stop_reason"] = "已读完当前筛选范围内的笔记" if count == total else "后台条数发生变化，请重新同步"
                break
            if count >= limit:
                result["stop_reason"] = "达到设定笔记上限"
                break
            next_page = page.locator(".d-pagination-page").last
            if "disabled" in (next_page.get_attribute("class") or ""):
                raise AccountReadError("翻页已结束，但已读取数与后台总数不一致，请重新同步。")
            next_page.click(timeout=5000)
            previous = payload["rows"][0]["title"] + payload["rows"][0]["date"]
            page.wait_for_function("old=>{const r=document.querySelector('table tbody tr');return r && (r.querySelector('.note-title')?.innerText.trim()+r.querySelector('.time')?.innerText.trim())!==old}", arg=previous, timeout=12000)
            page.wait_for_timeout(800)
        else:
            result["stop_reason"] = "达到本次翻页上限"
    except Exception as exc:
        if not result["overview"] and not result["notes"]:
            if isinstance(exc, AccountReadError):
                raise
            raise AccountReadError("后台数据尚未加载完成，请检查创作平台窗口后再同步。") from exc
        result["stop_reason"] = "读取中断，已保留此前确认的数据"
        result["warnings"].append(str(exc) if isinstance(exc, AccountReadError) else "页面或网络未完成加载，请检查专用窗口后再同步。")
    finally:
        if overview_page is not None:
            try:
                overview_page.close()
            except Exception:
                pass
    return result
