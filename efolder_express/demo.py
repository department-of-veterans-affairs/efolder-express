from twisted.internet.defer import succeed

from efolder_express.db import DownloadStatus


class DemoMemoryDatabase(object):
    def __init__(self):
        self._data = {
            "started": DownloadStatus(
                request_id="started",
                file_number="123456789",
                state="STARTED",
                documents=[],
            )
        }

    def get_download(self, logger, request_id):
        return succeed(self._data[request_id])
