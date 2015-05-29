from twisted.python.failure import Failure


def success_result_of(d):
    result = []
    d.addBoth(result.append)
    assert result
    if isinstance(result[0], Failure):
        result[0].raiseException()
    return result[0]


class FakeReactor(object):
    def callFromThread(self, f, *args, **kwargs):
        return f(*args, **kwargs)


class FakeThreadPool(object):
    def callInThreadWithCallback(self, cb, f, *args, **kwargs):
        try:
            result = f(*args, **kwargs)
        except Exception as e:
            cb(False, Failure(e))
        else:
            cb(True, result)
