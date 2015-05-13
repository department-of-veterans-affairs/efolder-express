import json
import time


def dict_merge(d1, d2):
    result = {}
    result.update(d1)
    result.update(d2)
    return result


class Timer(object):
    def __init__(self, logger, event, start_time):
        self.logger = logger
        self.event = event
        self.start_time = start_time

    def stop(self):
        duration = time.time() - self.start_time
        self.logger.bind(duration=duration).emit(self.event)


class Logger(object):
    def __init__(self, log, data=None):
        self._log = log
        self._data = data or {}

    def bind(self, **kwargs):
        return Logger(self._log, dict_merge(self._data, kwargs))

    def emit(self, event):
        self._log.msg(json.dumps(dict_merge(self._data, {"event": event})))

    def time(self, event):
        start = time.time()
        return Timer(self, event, start)
