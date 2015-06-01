from twisted.application.internet import SSLServer, TCPServer
from twisted.application.service import MultiService
from twisted.python import usage, log
from twisted.web.server import Site

from efolder_express.app import DownloadEFolder
from efolder_express.http import ForceHTTPSResource, HSTSResource
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
        options["config"],
    )
    app.start_fetch_document_types()

    service = MultiService()
    TCPServer(
        app.http_port,
        Site(ForceHTTPSResource(app.https_port), logPath="/dev/null"),
        reactor=reactor
    ).setServiceParent(service)

    SSLServer(
        app.https_port,
        Site(HSTSResource(app.app.resource()), logPath="/dev/null"),
        app.certificate_options,
        reactor=reactor,
    ).setServiceParent(service)

    return service
