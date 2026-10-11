"""Deterministic invented examples: no real account, personal data or external links."""
from io import BytesIO
from functools import lru_cache
import pandas as pd
from deployment import DEMO_NOTICE

SCENARIOS = {
    '职场知识创作者': ('个人创作者，职场博主，分享面试与求职知识', [
        ('简历优化', '简历优化：用项目经历说明能力', '面向求职新人，先整理岗位要求，再用项目过程说明自己的贡献。'),
        ('面试准备', '面试准备：回答项目复盘问题', '面向应届生，拆解面试问题，说明目标、执行过程与待改进之处。'),
        ('工作汇报', '工作汇报：把过程变成清晰结论', '我在职场学习如何汇报，先说结论，再补充证据，最后列出下一步。')]),
    '文创品牌': ('原创品牌，品牌官方账号，分享文创设计和手作过程', [
        ('手账拼贴', '手账拼贴：纸张与色彩搭配', '原创品牌分享手账拼贴步骤，从配色到纸张层次，展示设计过程。'),
        ('微缩造景', '微缩造景：桌面小世界制作', '我们品牌记录微缩造景过程，从构图到材料组合，文创作品可在店铺查看。'),
        ('新品设计', '新品设计：贴纸从草图到成品', '品牌官方介绍文创贴纸设计，展示草图、修改过程及使用场景。')]),
    '本地生活机构': ('官方机构，社区文化工作室，记录同城活动和到店体验', [
        ('社区活动', '社区活动：周末阅读交流', '工作室组织社区阅读活动，记录交流流程，适合想认识同城朋友的人。'),
        ('咖啡体验', '咖啡体验：门店空间观察', '同城咖啡店体验，介绍空间布局与到店路线，实际营业信息请向门店确认。'),
        ('手作课程', '手作课程：新手材料准备', '工作室分享手作课程的材料和练习过程，为第一次参加活动的人提供参考。')]),
    '生活方式博主': ('个人创作者，生活方式博主，记录独居与日常整理', [
        ('独居收纳', '独居收纳：小空间物品整理', '我在独居生活中练习收纳，先按使用频率分类，再调整摆放位置。'),
        ('周末旅行', '周末旅行：轻装出行清单', '旅行博主分享周末出行准备，根据天气与路线选择行李。'),
        ('日常料理', '日常料理：简单早餐搭配', '我的生活日常，记录早餐准备过程和食材搭配，不提供营养疗效承诺。')]),
}


def demo_frame(scenario):
    bio, themes = SCENARIOS[scenario]
    rows = []
    for i in range(18):
        theme, title, body = themes[i % len(themes)]
        rows.append({'账号名称': f'模拟账号·{scenario}', '账号简介': bio + '（虚构演示）',
                     '标题': f'{title}（模拟案例{i + 1}）', '正文': body + '\n' + DEMO_NOTICE,
                     '发布时间': f'2026-09-{i + 1:02d}', '图文/视频': '视频' if i % 3 == 1 else '图文',
                     '内容主题': theme, '点赞': 80 + (i * 137) % 1600,
                     '收藏': 15 + (i * 83) % 650, '评论': 2 + (i * 11) % 90,
                     '曝光': 2000 + i * 1600, '观看': 500 + i * 400, '涨粉': 2 + i * 3,
                     '数据性质': DEMO_NOTICE})
    # Deliberate missing/abbreviated/zero values demonstrate honest cleaning.
    rows[2]['点赞'] = '1.2万'
    rows[5]['收藏'] = None
    rows[8]['评论'] = '1千+'
    rows[11]['点赞'] = 0
    return pd.DataFrame(rows)


@lru_cache(maxsize=4)
def demo_workbook(scenario):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame({'说明': [DEMO_NOTICE, f'场景：{scenario}', '包含缺失、近似、下界和零值，用于演示清洗规则。']}).to_excel(writer, sheet_name='模拟数据说明', index=False)
        demo_frame(scenario).to_excel(writer, sheet_name='模拟笔记明细', index=False, startrow=2)
        writer.sheets['模拟笔记明细'].cell(1, 1, DEMO_NOTICE)
        writer.book.properties.creator = 'AI运营工作台·模拟数据'
    return output.getvalue()


class DemoUpload(BytesIO):
    def __init__(self, scenario):
        super().__init__(demo_workbook(scenario))
        self.name = f'模拟数据_{scenario}.xlsx'
