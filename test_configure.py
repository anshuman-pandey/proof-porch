from pathlib import Path
import os
import pytest
from werkzeug.security import check_password_hash
from scripts.configure import config_text, write_config


def test_generated_hash_and_cookie_defaults():
    config = dict(line.split('=', 1) for line in config_text('test-only-long-password').splitlines())
    assert config['COOKIE_SECURE'] == '1'
    assert check_password_hash(config['ADMIN_PASSWORD_HASH'].strip("'"), 'test-only-long-password')
    assert len(config['SECRET_KEY'].strip("'")) == 64
    assert 'test-only-long-password' not in str(config)
    assert 'COOKIE_SECURE=0' in config_text('test-only-long-password', True)


def test_refuse_short_password_and_secret_overwrite(tmp_path):
    with pytest.raises(ValueError):
        config_text('short')
    path = tmp_path / '.env'
    write_config(path, 'original')
    with pytest.raises(FileExistsError):
        write_config(path, 'replacement')
    assert path.read_text() == 'original'
    if os.name == 'posix':
        assert path.stat().st_mode & 0o777 == 0o600
