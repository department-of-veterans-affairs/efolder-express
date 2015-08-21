from twisted.application.internet import TCPServer
from twisted.application.service import MultiService, Service
from twisted.internet.defer import DeferredQueue, inlineCallbacks
from twisted.python import log, usage
from twisted.web.server import Site

from efolder_express.app import DownloadEFolder
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

    optFlags = [
        ["demo", None, "Run the server in demo mode, with no real data."],
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

    assert not (options["config"] and options["demo"])

    if options["demo"]:
        app = DownloadEFolder.create_demo(reactor, Logger(log))
    else:
        queue = DeferredQueue()
        app = DownloadEFolder.from_config(
            reactor,
            Logger(log),
            queue,
            options["config"],
        )

    if options.subCommand == "create-database":
        return CreateDatabaseService(reactor, app)

    if not options["demo"]:
        app.start_fetch_document_types()
        app.queue_pending_work()

    service = MultiService()
    TCPServer(
        8080,
        Site(app.app.resource(), logPath="/dev/null"),
        reactor=reactor
    ).setServiceParent(service)
    if not options["demo"]:
        for _ in xrange(8):
            DeferredQueueConsumerService(
                queue, lambda item: item()
            ).setServiceParent(service)
    return service
