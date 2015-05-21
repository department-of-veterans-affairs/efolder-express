from pathlib import Path

from twisted.application.internet import SSLServer, TCPServer
from twisted.application.service import MultiService
from twisted.python import usage, log
from twisted.web.server import Site

from efolder_express.app import DownloadEFolder
from efolder_express.log import Logger


class Options(usage.Options):
    optParameters = [
        ["config", "c", None, "Path to YAML config file."],
    ]


def makeService(options):
    from twisted.internet import reactor

    app = DownloadEFolder.from_config(
        reactor,
        Logger(log),
        Path(options["config"]),
    )
    app.start_fetch_document_types()
    site = Site(app.app.resource(), logPath="/dev/null")

    service = MultiService()
    TCPServer(8080, site, reactor=reactor).setServiceParent(service)
    SSLServer(
        8081,
        site,
        app.certificate_options,
        reactor=reactor,
    ).setServiceParent(service)


    return service
