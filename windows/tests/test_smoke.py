import sys

import app


def test_python_version():
    assert sys.version_info[:2] == (3, 11)


def test_app_package_importable():
    assert app.__name__ == "app"
