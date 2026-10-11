from pathlib import Path
import unittest
from unittest.mock import patch

import account_session
from account_reader import AccountReadError


class LoginStorageTests(unittest.TestCase):
    def test_cleanup_rejects_unrelated_directory(self):
        with self.assertRaisesRegex(AccountReadError, "路径异常"):
            account_session.remove_profile(Path.home())

    def test_cleanup_only_removes_dedicated_profile(self):
        profile = account_session.PROFILE_DIR
        with patch.object(Path, "resolve", return_value=profile), patch.object(Path, "is_symlink", return_value=False), patch.object(Path, "is_junction", return_value=False, create=True), patch.object(Path, "exists", return_value=True), patch("account_session.shutil.rmtree") as remove:
            account_session.remove_profile(profile)
            remove.assert_called_once_with(profile)

    def test_cleanup_rejects_redirected_profile(self):
        with patch.object(Path, "resolve", return_value=Path.home()), self.assertRaisesRegex(AccountReadError, "路径异常"), patch("account_session.shutil.rmtree") as remove:
            account_session.remove_profile(account_session.PROFILE_DIR)
            remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
