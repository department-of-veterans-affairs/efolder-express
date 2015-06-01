import json

from efolder_express.log import Logger


class FakeMemoryLog(object):
    def __init__(self):
        self.msgs = []

    def msg(self, s):
        self.msgs.append(json.loads(s))


class TestLogger(object):
    def test_emit(self):
        logger = Logger(FakeMemoryLog())
        logger.emit("test.event")
        assert logger._log.msgs == [{"event": "test.event"}]

    def test_bind(self):
        logger = Logger(FakeMemoryLog())
        logger.bind(key="value").emit("test.event1")
        logger.emit("test.event2")

        assert logger._log.msgs == [
            {"key": "value", "event": "test.event1"},
            {"event": "test.event2"},
        ]

    def test_time(self):
        logger = Logger(FakeMemoryLog())
        logger.time("test.event").stop()

        [msg] = logger._log.msgs
        assert set(msg) == {"event", "duration"}
        assert msg["event"] == "test.event"
        assert 0 < msg["duration"] < .1
