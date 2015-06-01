import pytest

from efolder_express.app import DownloadEFolder

from .utils import FakeVBMSClient, no_result, success_result_of


@pytest.fixture
def app():
    return DownloadEFolder(
        None,
        None,
        None,
        None,
        FakeVBMSClient(),
        None,
        None,
    )


class TestDownloadEFolder(object):
    def test_start_fetch_document_types(self, app):
        d = app.document_types.wait()
        no_result(d)

        d1 = app.start_fetch_document_types()
        success_result_of(d1)

        assert success_result_of(d) == {
            1: "Test!"
        }
