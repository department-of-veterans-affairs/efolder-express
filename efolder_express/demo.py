from twisted.internet.defer import succeed

from efolder_express.db import Document, DownloadStatus


class DemoMemoryDownloadDatabase(object):
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
