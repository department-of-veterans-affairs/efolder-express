from twisted.application.internet import TCPServer
from twisted.application.service import MultiService, Service
from twisted.internet.defer import inlineCallbacks, DeferredQueue
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


class DeferredQueueConsumerService(Service):
    def __init__(self, queue, handler):
        self.queue = queue
        self.handler = handler

    def startService(self):
        Service.startService(self)
        self.start_consume_queue()

    @inlineCallbacks
    def start_consume_queue(self):
        # Without any special termination logic, SIGINT kills the process
        # cleanly. So that seems sufficient.
        while True:
            item = yield self.queue.get()
            # TODO: error handling
            yield self.handler(item)


def makeService(options):
    from twisted.internet import reactor

    queue = DeferredQueue()
    app = DownloadEFolder.from_config(
        reactor,
        Logger(log),
        queue,
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
    for _ in xrange(8):
        DeferredQueueConsumerService(
            queue, lambda item: item()
        ).setServiceParent(service)
    return service
