import json

from twisted.internet.defer import succeed
from twisted.python.failure import Failure

from efolder_express.db import Document, DownloadStatus


def success_result_of(d):
    result = []
    d.addBoth(result.append)
    assert result
    if isinstance(result[0], Failure):
        result[0].raiseException()
    return result[0]


def no_result(d):
    result = []

    def cb(res):
        result.append(res)
        return res
    d.addBoth(cb)
    assert not result


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


class FakeMemoryLog(object):
    def __init__(self):
        self.msgs = []

    def msg(self, s):
        self.msgs.append(json.loads(s))


class FakeVBMSClient(object):
    def get_document_types(self, logger):
        return [
            {"type_id": "1", "description": "Test!"}
        ]


class FakeDownloadDatabase(object):
    def __init__(self):
        self._data = {
            "started": DownloadStatus(
                request_id="started",
                file_number="123456789",
                state="STARTED",
                documents=[],
            ),
            "manifest-downloaded": DownloadStatus(
                request_id="manifest-downloaded",
                file_number="123456789",
                state="MANIFEST_DOWNLOADED",
                documents=[
                    Document(
                        id="",
                        download_id="manifest-downloaded",
                        document_id="",
                        doc_type="",
                        filename="abc.pdf",
                        received_at=None,
                        source="",
                        content_location=None,
                        errored=False
                    ),
                ]
            ),
            "manifest-download-error": DownloadStatus(
                request_id="manifest-download-error",
                file_number="123456789",
                state="ERRORED",
                documents=[],
            )
        }

    def get_download(self, logger, request_id):
        return succeed(self._data[request_id])
