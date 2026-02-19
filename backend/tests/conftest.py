import pytest

from app.services.code_generator import CodeGenerator
from app.services.session_manager import SessionManager


@pytest.fixture
def code_generator():
    return CodeGenerator()


@pytest.fixture
def session_manager():
    return SessionManager()
