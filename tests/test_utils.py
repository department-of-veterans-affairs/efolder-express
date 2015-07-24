import pytest

from twisted.internet.defer import fail, succeed

from efolder_express.utils import DeferredValue

from .utils import no_result, success_result_of


class TestSuccessResultOf(object):
    def test_failure(self):
        with pytest.raises(ZeroDivisionError):
            success_result_of(fail(ZeroDivisionError()))

    def test_sucecss(self):
        assert success_result_of(succeed(12)) == 12


class TestDeferredValue(object):
    def test_simple(self):
        v = DeferredValue()

        d = v.wait()
        no_result(d)

        v.completed(12)
        assert success_result_of(d) == 12

        assert success_result_of(v.wait()) == 12
