from twisted.internet.defer import Deferred, succeed


class DeferredValue(object):
    def __init__(self):
        self._has_value = False
        self._value = None

        self._waiters = []

    def wait(self):
        if self._has_value:
            return succeed(self._value)
        else:
            d = Deferred()
            self._waiters.append(d)
            return d

    def completed(self, value):
        assert not self._has_value

        self._value = value
        self._has_value = True

        for d in self._waiters:
            d.callback(value)

        del self._waiters[:]
