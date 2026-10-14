import unittest
from unittest.mock import MagicMock
from playwright.sync_api import TimeoutError as BrowserTimeout
from account_reader import read_profile_page, AccountReadError, AccountAccessError
from profile_selectors import NOTE_ITEM, CARD_FIELDS, PROFILE_DESC, PROFILE_INTERACTIONS

URL='https://www.xiaohongshu.com/user/profile/aaaaaaaaaaaaaaaaaaaaaaaa'

def page_with(cards, count=1):
    page=MagicMock(); page.url=URL; page.is_closed.return_value=False
    body=MagicMock(); body.inner_text.return_value='模拟账号的主页与笔记'
    dialog=MagicMock(); dialog.filter.return_value.count.return_value=0
    notes=MagicMock(); notes.count.return_value=count; notes.evaluate_all.return_value=cards
    blank=MagicMock(); blank.count.return_value=0
    page.locator.side_effect=lambda selector: body if selector=='body' else notes if selector==NOTE_ITEM else blank if selector in [PROFILE_DESC,PROFILE_INTERACTIONS] else dialog
    page.title.return_value='模拟账号 - 小红书'
    return page,notes,body,dialog

class ProfileLayoutTests(unittest.TestCase):
    def test_normal_missing_likes_remain_valid_and_selector_config_passed(self):
        page,notes,_,_=page_with([{'title':'真实标题','likes':'','href':'','cover':''}])
        result=read_profile_page(page,URL)
        self.assertEqual(result['name'],'模拟账号')
        self.assertIsNone(result['notes'][0]['点赞'])
        self.assertEqual(notes.evaluate_all.call_args.args[1]['fields'],CARD_FIELDS)
        page.unroute.assert_called_once()

    def test_zero_cards_after_wait_is_layout_error(self):
        page,notes,_,_=page_with([],0)
        notes.first.wait_for.side_effect=BrowserTimeout('timeout')
        with self.assertRaisesRegex(AccountReadError,'结构可能已变化.*反馈'):
            read_profile_page(page,URL)
        notes.evaluate_all.assert_not_called(); page.unroute.assert_called_once()

    def test_present_cards_empty_fields_is_layout_error(self):
        page,_,_,_=page_with([{'title':'','likes':''}])
        with self.assertRaisesRegex(AccountReadError,'页面可能已改版.*反馈'):
            read_profile_page(page,URL)
        page.unroute.assert_called_once()

    def test_restriction_precedes_layout_and_login_stops(self):
        for login in [False, True]:
            page,notes,body,dialog=page_with([],0)
            if login:
                dialog.filter.return_value.count.return_value=1
                dialog.filter.return_value.nth.return_value.is_visible.return_value=True
            else: body.inner_text.return_value='安全验证'
            with self.assertRaises(AccountAccessError): read_profile_page(page,URL)
            notes.evaluate_all.assert_not_called()

    def test_exception_never_returns_partial_result(self):
        page,notes,_,_=page_with([{'title':'标题','likes':'42'}])
        notes.evaluate_all.side_effect=RuntimeError('closed')
        with self.assertRaisesRegex(AccountReadError,'未保存部分结果'):
            read_profile_page(page,URL)
