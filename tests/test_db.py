import pytest

from sqlalchemy.schema import CreateTable
from sqlalchemy.sql import select, func

from efolder_express.db import DownloadDatabase

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
