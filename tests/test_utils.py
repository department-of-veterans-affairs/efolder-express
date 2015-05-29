import pytest

from twisted.internet.defer import fail, succeed

from .utils import success_result_of


class TestSuccessResultOf(object):
    def test_failure(self):
        with pytest.raises(ZeroDivisionError):
            success_result_of(fail(ZeroDivisionError()))

    def test_sucecss(self):
        assert success_result_of(succeed(12)) == 12
