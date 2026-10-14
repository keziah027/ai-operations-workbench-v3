"""公开主页 DOM 适配点；不使用 selectors.py，避免遮蔽 Python 标准库。"""
NOTE_ITEM = "section.note-item"
CARD_FIELDS = {
    'title': '.title', 'likes': '.like-wrapper .count',
    'link': 'a.cover[href]', 'fallback_link': 'a[href]', 'image': 'a.cover img',
}
PROFILE_INTERACTIONS = '.user-interactions'
PROFILE_DESC = '.user-desc'
