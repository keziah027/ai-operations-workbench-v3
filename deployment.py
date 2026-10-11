"""Public-by-default deployment policy. Local desktop features require explicit opt-in."""
import os


def public_mode():
    return os.environ.get('APP_MODE', 'public').strip().lower() != 'local'


DEMO_NOTICE = '模拟数据，仅用于功能演示；不代表真实账号表现或运营成果。'
