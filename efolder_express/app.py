import functools
import os
import uuid

from cryptography import fernet

import jinja2

import klein

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python.filepath import FilePath
from twisted.python.threadpool import ThreadPool
from twisted.web.static import File

import yaml

from efolder_express.db import DownloadDatabase, Document
from efolder_express.utils import DeferredValue
from efolder_express.vbms import VBMSClient, VBMSError


def instrumented_route(func):
    @functools.wraps(func)
    def route(self, request, *args, **kwargs):
        timer = self.logger.bind(
            peer=request.getClientIP(),
        ).time("request.{}".format(func.__name__))
        request.notifyFinish().addBoth(lambda *args, **kwargs: timer.stop())
        return func(self, request, *args, **kwargs)
    return route


class DownloadEFolder(object):
    app = klein.Klein()

    def __init__(self, logger, download_database, storage_path, fernet,
                 vbms_client, queue):
        self.logger = logger
        self.download_database = download_database
        self.storage_path = storage_path
        self.fernet = fernet
        self.vbms_client = vbms_client
        self.queue = queue

        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                FilePath(__file__).parent().parent().child("templates").path,
            ),
            autoescape=True
        )
        self.document_types = DeferredValue()

    @classmethod
    def from_config(cls, reactor, logger, queue, config_path):
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # TODO: bump this once alchimia properly handles pinning
        thread_pool = ThreadPool(minthreads=1, maxthreads=1)
        thread_pool.start()
        reactor.addSystemEventTrigger('during', 'shutdown', thread_pool.stop)

        return cls(
            logger,
            DownloadDatabase(reactor, thread_pool, config["db"]["uri"]),
            FilePath(config["storage"]["filesystem"]),
            fernet.MultiFernet([
                fernet.Fernet(key) for key in config["encryption_keys"]
            ]),
            VBMSClient(
                reactor,
                connect_vbms_path=config["connect_vbms"]["path"],
                bundle_path=config["connect_vbms"]["bundle_path"],
                endpoint_url=config["vbms"]["endpoint_url"],
                keyfile=config["vbms"]["keyfile"],
                samlfile=config["vbms"]["samlfile"],
                key=config["vbms"].get("key"),
                keypass=config["vbms"]["keypass"],
                ca_cert=config["vbms"].get("ca_cert"),
                client_cert=config["vbms"].get("client_cert"),
            ),
            queue,
        )

    def render_template(self, template_name, data={}):
        t = self.jinja_env.get_template(template_name)
        return t.render(data)

    @inlineCallbacks
    def start_download(self, file_number, request_id):
        logger = self.logger.bind(
            file_number=file_number, request_id=request_id
        )

        logger.emit("list_documents.start")
        try:
            documents = yield self.vbms_client.list_documents(
                logger, file_number
            )
        except VBMSError as e:
            logger.bind(
                stdout=e.stdout,
                stderr=e.stderr,
                exit_code=e.exit_code,
            ).emit("list_documents.error")
            yield self.download_database.mark_download_errored(request_id)
        else:
            logger.emit("list_documents.success")

            documents = [
                Document.from_json(request_id, doc)
                for doc in documents
            ]
            yield self.download_database.create_documents(documents)
            for doc in documents:
                self.queue.put(functools.partial(
                    self.start_file_download, logger, doc
                ))
            yield self.download_database.mark_download_manifest_downloaded(
                request_id
            )

    @inlineCallbacks
    def start_file_download(self, logger, document):
        logger = logger.bind(document_id=document.document_id)
        logger.emit("get_document.start")

        try:
            contents = yield self.vbms_client.fetch_document_contents(
                logger, str(document.document_id)
            )
        except VBMSError as e:
            logger.bind(
                stdout=e.stdout,
                stderr=e.stderr,
                exit_code=e.exit_code,
            ).emit("get_document.error")
            yield self.download_database.mark_document_errored(document)
        else:
            logger.emit("get_document.success")
            target = self.storage_path.child(str(uuid.uuid4()))
            target.setContent(self.fernet.encrypt(contents))
            yield self.download_database.set_document_content_location(
                document, target.path
            )

    @inlineCallbacks
    def start_fetch_document_types(self):
        document_types = yield self.vbms_client.get_document_types(self.logger)
        self.document_types.completed({
            int(c["type_id"]): c["description"]
            for c in document_types
        })

    @inlineCallbacks
    def enqueue_pending_work(self):
        downloads, documents = yield self.db.get_pending_work()
        for download in downloads:
            self.queue.put(functools.partial(
                self.start_download, download.file_number, download.request_id,
            ))
        for document in documents:
            # TODO: self.logger doesn't include any info about the
            # DownloadStatus. When triggered from the "usual" path it has
            # ``file_number`` and ``request_id`` keys.
            self.queue.put(functools.partial(
                self.start_file_download, self.logger, document
            ))

    @app.route("/")
    @instrumented_route
    def root(self, request):
        request.redirect("/efolder-express/")
        return succeed(None)

    @app.route("/efolder-express/")
    @instrumented_route
    def index(self, request):
        return self.render_template("index.html")

    @app.route("/efolder-express/download/", methods=["POST"])
    @instrumented_route
    @inlineCallbacks
    def download(self, request):
        file_number = request.args["file_number"][0]
        file_number = file_number.replace("-", "").replace(" ", "")

        request_id = str(uuid.uuid4())

        yield self.download_database.create_download(request_id, file_number)
        self.queue.put(functools.partial(
            self.start_download, file_number, request_id
        ))

        request.redirect("/efolder-express/download/{}/".format(request_id))
        returnValue(None)

    @app.route("/efolder-express/download/<request_id>/")
    @instrumented_route
    @inlineCallbacks
    def download_status(self, request, request_id):
        download = yield self.download_database.get_download(
            request_id=request_id
        )
        returnValue(self.render_template("download.html", {
            "status": download
        }))

    @app.route("/efolder-express/download/<request_id>/zip/")
    @instrumented_route
    @inlineCallbacks
    def download_zip(self, request, request_id):
        download = yield self.download_database.get_download(
            request_id=request_id
        )
        assert download.completed

        self.logger.bind(
            request_id=request_id,
            file_number=download.file_number,
        ).emit("download")

        document_types = yield self.document_types.wait()
        path = download.build_zip(self.jinja_env, self.fernet, document_types)

        request.setHeader(
            "Content-Disposition",
            "attachment; filename={}-eFolder.zip".format(download.file_number)
        )

        resource = File(path, defaultType="application/zip")
        resource.isLeaf = True

        request.notifyFinish().addBoth(lambda *args, **kwargs: os.remove(path))

        returnValue(resource)
