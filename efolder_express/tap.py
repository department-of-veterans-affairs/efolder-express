from twisted.application.internet import TCPServer
from twisted.application.service import MultiService, Service
from twisted.internet.defer import inlineCallbacks
from twisted.python import usage, log
from twisted.web.server import Site

from efolder_express.app import DownloadEFolder
from efolder_express.http import HSTSResource
from efolder_express.log import Logger


class CreateDatabaseOptions(usage.Options):
    pass


class Options(usage.Options):
    subCommands = [
        [
            "create-database",
            None,
            CreateDatabaseOptions,
            "Create the database"
        ],
    ]

    optParameters = [
        ["config", "c", None, "Path to YAML config file."],
    ]


class CreateDatabaseService(Service):
    def __init__(self, reactor, app):
        self.reactor = reactor
        self.app = app

    def startService(self):
        Service.startService(self)
        self.start_create_tables()

    @inlineCallbacks
    def start_create_tables(self):
        try:
            yield self.app.download_database.create_database()
        finally:
            self.reactor.stop()


def makeService(options):
    from twisted.internet import reactor

    app = DownloadEFolder.from_config(
        reactor,
        Logger(log),
        options["config"],
    )

    if options.subCommand == "create-database":
        return CreateDatabaseService(reactor, app)

    app.start_fetch_document_types()

    service = MultiService()
    TCPServer(
        8080,
        Site(HSTSResource(app.app.resource()), logPath="/dev/null"),
        reactor=reactor
    ).setServiceParent(service)
    return service
