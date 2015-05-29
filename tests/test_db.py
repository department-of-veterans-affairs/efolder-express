import datetime

import pytest

from sqlalchemy.schema import CreateTable

from efolder_express.db import DownloadDatabase, DownloadNotFound, Document

from .utils import FakeReactor, FakeThreadPool, success_result_of


@pytest.fixture
def db():
    db = DownloadDatabase(FakeReactor(), FakeThreadPool(), "sqlite://")
    for table in [db._downloads, db._documents]:
        success_result_of(db._engine.execute(CreateTable(table)))
    return db


class TestDownloadDatabase(object):
    def scalar(self, db, q):
        d = db._engine.execute(q)
        result = success_result_of(d)
        return success_result_of(result.scalar())

    def test_create_download(self, db):
        d = db.create_download("test-request-id", "123456789")
        success_result_of(d)
        assert self.scalar(db, db._downloads.select().count()) == 1

        d = db.create_download("test-request-id-2", "987654321")
        success_result_of(d)
        assert self.scalar(db, db._downloads.select().count()) == 2

    def test_get_download(self, db):
        d = db.create_download("test-request-id", "123456789")
        success_result_of(d)

        download = success_result_of(db.get_download("test-request-id"))
        assert download.request_id == "test-request-id"
        assert download.file_number == "123456789"
        assert download.state == "STARTED"
        assert download.documents == []

        assert not download.completed
        assert download.percent_completed == 5

    def test_get_download_non_existent(self, db):
        d = db.get_download("non-existent")
        with pytest.raises(DownloadNotFound):
            success_result_of(d)

    def test_mark_download_errored(self, db):
        d = db.create_download("test-request-id", "123456789")
        success_result_of(d)

        d = db.mark_download_errored("test-request-id")
        success_result_of(d)

        download = success_result_of(db.get_download("test-request-id"))
        assert download.state == "ERRORED"

    def test_create_documents(self, db):
        d = db.create_download("test-request-id", "123456789")
        success_result_of(d)

        db.create_documents([
            Document(
                id="test-document-id",
                download_id="test-request-id",
                document_id="{ABCD}",
                doc_type="00356",
                filename="file.pdf",
                received_at=datetime.datetime.utcnow(),
                source="CUI",
                content_location=None,
                errored=False,
            )
        ])

        download = success_result_of(db.get_download("test-request-id"))
        assert len(download.documents) == 1
        assert not download.completed
        assert download.percent_completed == 0

        [doc] = download.documents
        assert doc.id == "test-document-id"
