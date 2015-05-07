import datetime
import io
import json
import os
import stat
import sys
import tempfile
import uuid
import zipfile

import jinja2

import klein

from pathlib import Path

from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet.task import react
from twisted.internet.utils import getProcessOutput
from twisted.python import log
from twisted.web.server import Site

import yaml


class Document(object):
    def __init__(self, document_id, doc_type, filename, received_at, source):
        self.document_id = document_id
        self.doc_type = doc_type
        self.filename = filename
        self.received_at = received_at
        self.source = source

        self.completed = False
        self.errored = False

    @classmethod
    def from_json(cls, data):
        return cls(
            data["document_id"],
            data["doc_type"],
            data["filename"],
            datetime.datetime.strptime(data["received_at"], "%Y-%m-%d").date(),
            data["source"],
        )


class DownloadStatus(object):
    def __init__(self, jinja_env, file_number, request_id):
        self.jinja_env = jinja_env

        self.file_number = file_number
        self.request_id = request_id

        self.has_manifest = False
        self.manifest = []
        self.errored = None

        self._io = io.BytesIO()
        self.zipfile = zipfile.ZipFile(self._io, "w")

    @property
    def _completed_count(self):
        return sum(1 for doc in self.manifest if doc.completed or doc.errored)

    @property
    def completed(self):
        return self.manifest and self._completed_count == len(self.manifest)

    @property
    def percent_completed(self):
        if not self.manifest:
            return 5
        return int(100 * (self._completed_count / float(len(self.manifest))))

    def add_document(self, document):
        self.has_manifest = True
        self.manifest.append(document)

    def add_document_contents(self, document, contents):
        self.zipfile.writestr(
            "{}-eFolder/{}".format(self.file_number, document.filename),
            contents
        )
        document.completed = True

    def finalize_zip_contents(self):
        readme_template = self.jinja_env.get_template("readme.txt")
        self.zipfile.writestr(
            "{}-eFolder/README.txt".format(self.file_number),
            readme_template.render({"status": self}).encode(),
        )
        self.zipfile.close()
        return self._io.getvalue()


class DownloadEFolder(object):
    app = klein.Klein()

    def __init__(self, reactor, connect_vbms_path, bundle_path, endpoint_url,
                 keyfile, samlfile, key, keypass, ca_cert, client_cert):
        self.reactor = reactor
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
                str(Path(__file__).parent.joinpath("templates")),
            ),
            autoescape=True
        )

        self.download_status = {}

    @classmethod
    def from_config(cls, reactor, config_path):
        with config_path.open() as f:
            config = yaml.safe_load(f)
        return cls(
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
        )

    def render_template(self, template_name, data={}):
        t = self.jinja_env.get_template(template_name)
        return t.render(data)

    def _path_to_ruby(self, path):
        if path is None:
            return "nil"
        else:
            return repr(path)

    def _execute_connect_vbms(self, request, formatter):
        ruby_code = """#!/usr/bin/env ruby

require 'json'

require '{connect_vbms_path}/src/vbms.rb'

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

        return getProcessOutput(
            self._bundle_path,
            ["exec", f.name],
            env=os.environ,
            path=self._connect_vbms_path,
            reactor=self.reactor
        )

    @inlineCallbacks
    def start_download(self, file_number, request_id):
        status = DownloadStatus(self.jinja_env, file_number, request_id)
        self.download_status[request_id] = status

        log.msg(json.dumps({
            "event": "list_documents.start",
            "request_id": request_id,
            "file_number": file_number,
        }))
        try:
            documents = json.loads((yield self._execute_connect_vbms(
                "VBMS::Requests::ListDocuments.new({!r})".format(file_number),
                'result.map(&:to_h).to_json'
            )))
        except IOError:
            log.msg(json.dumps({
                "event": "list_documents.error",
                "file_number": file_number,
                "request_id": request_id,
            }))
            log.err()
            status.errored = True
        else:
            log.msg(json.dumps({
                "event": "list_documents.success",
                "file_number": file_number,
                "request_id": request_id,
            }))

            for doc in documents:
                document = Document.from_json(doc)
                status.add_document(document)

                self.start_file_download(status, document)

    @inlineCallbacks
    def start_file_download(self, status, document):
        log.msg(json.dumps({
            "event": "get_document.start",
            "request_id": status.request_id,
            "file_number": status.file_number,
            "document_id": document.document_id,
        }))
        try:
            contents = yield self._execute_connect_vbms(
                "VBMS::Requests::FetchDocumentById.new({!r})".format(str(document.document_id)),
                "result.content",
            )
        except IOError:
            log.err()
            log.msg(json.dumps({
                "event": "get_document.error",
                "request_id": status.request_id,
                "file_number": status.file_number,
                "document_id": document.document_id,
            }))
            document.errored = True
        else:
            log.msg(json.dumps({
                "event": "get_document.success",
                "request_id": status.request_id,
                "file_number": status.file_number,
                "document_id": document.document_id,
            }))
            status.add_document_contents(document, contents)

    @app.route("/")
    def index(self, request):
        return self.render_template("index.html")

    @app.route("/download/", methods=["POST"])
    def download(self, request):
        file_number = request.args["file_number"][0]

        request_id = str(uuid.uuid4())

        self.start_download(file_number, request_id)

        request.redirect("/download/{}/".format(request_id))
        return succeed(None)

    @app.route("/download/<request_id>/")
    def download_status(self, request, request_id):
        status = self.download_status[request_id]
        return self.render_template("download.html", {"status": status})

    @app.route("/download/<request_id>/zip/")
    def download_zip(self, request, request_id):
        status = self.download_status[request_id]
        assert status.completed

        request.setHeader("Content-Type", "application/zip")

        del self.download_status[request_id]
        return status.finalize_zip_contents()


def main(reactor):
    log.startLogging(sys.stdout)
    app = DownloadEFolder.from_config(
        reactor,
        Path(__file__).parent.joinpath("config", "test.yml"),
    )
    reactor.listenTCP(8080, Site(app.app.resource(), logPath="/dev/null"), interface="localhost")
    return Deferred()


if __name__ == "__main__":
    react(main, sys.argv[1:])
