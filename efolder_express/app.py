import functools
import os
import tempfile
import uuid

from cryptography import fernet

import jinja2

import klein

from twisted.internet import ssl
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log
from twisted.python.filepath import FilePath
from twisted.python.threadpool import ThreadPool
from twisted.web.static import File

import yaml

from efolder_express.db import DownloadDatabase, Document
from efolder_express.utils import DeferredValue
from efolder_express.vbms import VBMSClient


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

    def __init__(self, logger, download_database, fernet, certificate_options,
                 vbms_client, http_port, https_port):
        self.logger = logger
        self.download_database = download_database
        self.fernet = fernet
        self.certificate_options = certificate_options
        self.vbms_client = vbms_client

        self.http_port = http_port
        self.https_port = https_port

        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                FilePath(__file__).parent().parent().child("templates").path,
            ),
            autoescape=True
        )
        self.document_types = DeferredValue()

    @classmethod
    def from_config(cls, reactor, logger, config_path):
        with open(config_path) as f:
            config = yaml.safe_load(f)

        with open(config["tls"]["certificate"]) as f:
            certificate = ssl.PrivateCertificate.loadPEM(f.read())

        certificate_options = ssl.CertificateOptions(
            privateKey=certificate.privateKey.original,
            certificate=certificate.original,
            dhParameters=ssl.DiffieHellmanParameters.fromFile(
                FilePath(config["tls"]["dh_parameters"]),
            )
        )

        # TODO: bump this once alchimia properly handles pinning
        thread_pool = ThreadPool(minthreads=1, maxthreads=1)
        thread_pool.start()
        reactor.addSystemEventTrigger('during', 'shutdown', thread_pool.stop)

        return cls(
            logger,
            DownloadDatabase(reactor, thread_pool, config["db"]["uri"]),
            fernet.MultiFernet([
                fernet.Fernet(key) for key in config["encryption_keys"]
            ]),
            certificate_options,
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
            config["http"]["http_port"],
            config["http"]["https_port"],
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
        except IOError:
            logger.emit("list_documents.error")
            log.err()
            yield self.download_database.mark_download_errored(request_id)
        else:
            logger.emit("list_documents.success")

            documents = [
                Document.from_json(request_id, doc)
                for doc in documents
            ]
            yield self.download_database.create_documents(documents)
            for doc in documents:
                self.start_file_download(logger, request_id, doc)

    @inlineCallbacks
    def start_file_download(self, logger, request_id, document):
        logger = logger.bind(document_id=document.document_id)
        logger.emit("get_document.start")

        try:
            contents = yield self.vbms_client.fetch_document_contents(
                logger, str(document.document_id)
            )
        except IOError:
            logger.emit("get_document.error")
            log.err()
            yield self.download_database.mark_document_errored(document)
        else:
            logger.emit("get_document.success")
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(self.fernet.encrypt(contents))
            yield self.download_database.set_document_content_location(
                document, f.name
            )

    @inlineCallbacks
    def start_fetch_document_types(self):
        document_types = yield self.vbms_client.get_document_types(self.logger)
        self.document_types.completed({
            int(c["type_id"]): c["description"]
            for c in document_types
        })

    @app.route("/")
    @instrumented_route
    def index(self, request):
        return self.render_template("index.html")

    @app.route("/download/", methods=["POST"])
    @instrumented_route
    @inlineCallbacks
    def download(self, request):
        file_number = request.args["file_number"][0]
        file_number = file_number.replace("-", "").replace(" ", "")

        request_id = str(uuid.uuid4())

        yield self.download_database.create_download(request_id, file_number)
        self.start_download(file_number, request_id).addErrback(log.err)

        request.redirect("/download/{}/".format(request_id))
        returnValue(None)

    @app.route("/download/<request_id>/")
    @instrumented_route
    @inlineCallbacks
    def download_status(self, request, request_id):
        download = yield self.download_database.get_download(
            request_id=request_id
        )
        returnValue(self.render_template("download.html", {
            "status": download
        }))

    @app.route("/download/<request_id>/zip/")
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
