import pytest
from app.models.enums import Role

def test_roles_exist():
    assert Role.ADMIN == "ADMIN"
    assert Role.OPERATOR == "OPERATOR"
    assert Role.AUDITOR == "AUDITOR"
