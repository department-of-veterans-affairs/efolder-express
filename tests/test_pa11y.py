import os

import pytest

from twisted.internet.defer import inlineCallbacks, succeed
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.utils import getProcessOutputAndValue
from twisted.python.procutils import which
from twisted.web.server import Site

from efolder_express.app import DownloadEFolder
from efolder_express.log import Logger

from .utils import FakeMemoryLog


@pytest.fixture
def reactor():
    from twisted.internet import reactor
    return reactor


@pytest.fixture
def server(request, reactor):
    logger = Logger(FakeMemoryLog())
    app = DownloadEFolder(
        logger=logger,
        download_database=None,
        storage_path=None,
        fernet=None,
        vbms_client=None,
        queue=None,
        env_name="testing",
    )
    endpoint = TCP4ServerEndpoint(reactor, 0)
    d = endpoint.listen(Site(app.app.resource(), logPath="/dev/null"))

    def addfinalizer(port):
        # Add a callback so that the server is shutdown at the end of the test.
        request.addfinalizer(port.stopListening)
        return port

    d.addCallback(addfinalizer)
    return pytest.blockon(d)


class TestAccessibility(object):
    @inlineCallbacks
    def _pa11y_test(self, reactor, server, url):
        stdout, stderr, exit_code = yield getProcessOutputAndValue(
            which("pa11y")[0], [
                "--level=error",
                "--standard=Section508",
                "http://127.0.0.1:{}{}".format(server.getHost().port, url),
            ],
            reactor=reactor,
            env=os.environ,
        )
        assert exit_code == 0

    @pytest.inlineCallbacks
    def test_index(self, reactor, server):
        yield self._pa11y_test(reactor, server, "/efolder-express/")
