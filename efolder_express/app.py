import json
import os
import stat
import tempfile
import uuid

import jinja2

import klein

from twisted.internet import ssl
from twisted.internet.defer import (
    DeferredSemaphore, inlineCallbacks, returnValue
)
from twisted.internet.utils import getProcessOutput
from twisted.python import log
from twisted.python.filepath import FilePath
from twisted.web.static import File

import yaml

from efolder_express.db import DownloadDatabase, Document
from efolder_express.utils import DeferredValue


class DownloadEFolder(object):
    app = klein.Klein()

    def __init__(self, reactor, logger, download_database, certificate_options,
                 connect_vbms_path, bundle_path, endpoint_url, keyfile,
                 samlfile, key, keypass, ca_cert, client_cert):
        self.reactor = reactor
        self.logger = logger
        self.download_database = download_database
        self.certificate_options = certificate_options

        self._connect_vbms_path = connect_vbms_path
        self._bundle_path = bundle_path
        self._endpoint_url = endpoint_url
        self._keyfile = keyfile
        self._samlfile = samlfile
        self._key = key
        self._keypass = keypass
        self._ca_cert = ca_cert
        self._client_cert = client_cert

        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                FilePath(__file__).parent().parent().child("templates").path,
            ),
            autoescape=True
        )
        self._connect_vbms_semaphore = DeferredSemaphore(tokens=8)

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

        return cls(
            reactor,
            logger,
            DownloadDatabase(reactor, config["db"]["uri"]),
            certificate_options,
            connect_vbms_path=config["connect_vbms"]["path"],
            bundle_path=config["connect_vbms"]["bundle_path"],
            endpoint_url=config["vbms"]["endpoint_url"],
            keyfile=config["vbms"]["keyfile"],
            samlfile=config["vbms"]["samlfile"],
            key=config["vbms"].get("key"),
            keypass=config["vbms"]["keypass"],
            ca_cert=config["vbms"].get("ca_cert"),
            client_cert=config["vbms"].get("client_cert"),
        )

    def render_template(self, template_name, data={}):
        t = self.jinja_env.get_template(template_name)
        return t.render(data)

    def _path_to_ruby(self, path):
        if path is None:
            return "nil"
        else:
            return repr(path)

    def _execute_connect_vbms(self, logger, request, formatter, args):
        ruby_code = """#!/usr/bin/env ruby

$LOAD_PATH << '{connect_vbms_path}/src/'

require 'json'

require 'vbms'


client = VBMS::Client.new(
    {endpoint_url!r},
    {keyfile},
    {samlfile},
    {key},
    {keypass!r},
    {ca_cert},
    {client_cert},
)
request = {request}
result = client.send(request)
STDOUT.write({formatter})
STDOUT.flush()
        """.format(
            connect_vbms_path=self._connect_vbms_path,
            endpoint_url=self._endpoint_url,
            keyfile=self._path_to_ruby(self._keyfile),
            samlfile=self._path_to_ruby(self._samlfile),
            key=self._path_to_ruby(self._key),
            keypass=self._keypass,
            ca_cert=self._path_to_ruby(self._ca_cert),
            client_cert=self._path_to_ruby(self._client_cert),

            request=request,
            formatter=formatter,
        ).strip()
        with tempfile.NamedTemporaryFile(suffix=".rb", delete=False) as f:
            f.write(ruby_code)

        st = os.stat(f.name)
        os.chmod(f.name, st.st_mode | stat.S_IEXEC)

        @inlineCallbacks
        def run():
            timer = logger.time("process.spawn")
            try:
                result = yield getProcessOutput(
                    self._bundle_path,
                    ["exec", f.name] + args,
                    env=os.environ,
                    path=self._connect_vbms_path,
                    reactor=self.reactor
                )
            finally:
                timer.stop()
            returnValue(result)

        return self._connect_vbms_semaphore.run(run)

    @inlineCallbacks
    def start_download(self, file_number, request_id):
        logger = self.logger.bind(
            file_number=file_number, request_id=request_id
        )

        logger.emit("list_documents.start")
        try:
            documents = json.loads((yield self._execute_connect_vbms(
                logger.bind(process="ListDocuments"),
                "VBMS::Requests::ListDocuments.new(ARGV[0])",
                'result.map(&:to_h).to_json',
                [file_number],
            )))
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
            contents = yield self._execute_connect_vbms(
                logger.bind(process="FetchDocumentById"),
                "VBMS::Requests::FetchDocumentById.new(ARGV[0])",
                "result.content",
                [str(document.document_id)],
            )
        except IOError:
            logger.emit("get_document.error")
            log.err()
            yield self.download_database.mark_document_errored(document)
        else:
            logger.emit("get_document.success")
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(contents)
            yield self.download_database.set_document_content_location(
                document, f.name
            )

    @inlineCallbacks
    def start_fetch_document_types(self):
        contents = json.loads((yield self._execute_connect_vbms(
            self.logger.bind(process="GetDocumentTypes"),
            "VBMS::Requests::GetDocumentTypes.new()",
            "result.map(&:to_h).to_json",
            [],
        )))
        self.document_types.completed({
            int(c["type_id"]): c["description"]
            for c in contents
        })

    @app.route("/")
    def index(self, request):
        return self.render_template("index.html")

    @app.route("/download/", methods=["POST"])
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
    @inlineCallbacks
    def download_status(self, request, request_id):
        download = yield self.download_database.get_download(
            request_id=request_id
        )
        returnValue(self.render_template("download.html", {
            "status": download
        }))

    @app.route("/download/<request_id>/zip/")
    @inlineCallbacks
    def download_zip(self, request, request_id):
        download = yield self.download_database.get_download(
            request_id=request_id
        )
        assert download.completed

        document_types = yield self.document_types.wait()
        path = download.build_zip(self.jinja_env, document_types)

        request.setHeader(
            "Content-Disposition",
            "attachment; filename={}-eFolder.zip".format(download.file_number)
        )

        resource = File(path, defaultType="application/zip")
        resource.isLeaf = True
        returnValue(resource)
