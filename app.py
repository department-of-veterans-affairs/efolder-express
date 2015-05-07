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


class Document(object):
    def __init__(self, document_id, doc_type, filename, received_at, source):
        self.document_id = document_id
        self.doc_type = doc_type
        self.filename = filename
        self.received_at = received_at
        self.source = source

        self.completed = False

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

        self._io = io.BytesIO()
        self.zipfile = zipfile.ZipFile(self._io, "w")

    @property
    def _completed_count(self):
        return sum(1 for doc in self.manifest if doc.completed)

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
        self.zipfile.writestr(
            "{}-eFolder/README.txt".format(self.file_number),
            self.jinja_env.get_template("readme.txt").render({"status": self}).encode(),
        )
        self.zipfile.close()
        return self._io.getvalue()


class DownloadEFolder(object):
    app = klein.Klein()

    def __init__(self, reactor, connect_vbms_path, endpoint_url, keyfile,
                 samlfile, key):
        self.reactor = reactor
        self._connect_vbms_path = connect_vbms_path
        self._endpoint_url = endpoint_url
        self._keyfile = keyfile
        self._samlfile = samlfile
        self._key = key

        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                str(Path(__file__).parent.joinpath("templates")),
            ),
            autoescape=True
        )

        self.download_status = {}

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
    "importkey",
    nil,
    nil,
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

            request=request,
            formatter=formatter,
        ).strip()
        with tempfile.NamedTemporaryFile(suffix=".rb", delete=False) as f:
            f.write(ruby_code)

        st = os.stat(f.name)
        os.chmod(f.name, st.st_mode | stat.S_IEXEC)

        return getProcessOutput(
            "/Users/alex_gaynor/.gem/ruby/2.0.0/bin/bundle",
            ["exec", f.name],
            env=os.environ,
            path=self._connect_vbms_path,
            reactor=self.reactor
        )

    @inlineCallbacks
    def start_download(self, file_number, request_id):
        status = DownloadStatus(self.jinja_env, file_number, request_id)
        self.download_status[request_id] = status

        documents = json.loads((yield self._execute_connect_vbms(
            "VBMS::Requests::ListDocuments.new({!r})".format(file_number),
            'result.map(&:to_h).to_json'
        )))

        for doc in documents:
            document = Document.from_json(doc)
            status.add_document(document)

            self.start_file_download(status, document).addErrback(log.err)

    @inlineCallbacks
    def start_file_download(self, status, document):
        contents = yield self._execute_connect_vbms(
            "VBMS::Requests::FetchDocumentById.new({!r})".format(str(document.document_id)),
            "result.content",
        )
        status.add_document_contents(document, contents)

    @app.route("/")
    def index(self, request):
        return self.render_template("index.html")

    @app.route("/download/", methods=["POST"])
    def download(self, request):
        file_number = request.args["file_number"][0]

        request_id = str(uuid.uuid4())

        self.start_download(file_number, request_id).addErrback(log.err)

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
    app = DownloadEFolder(
        reactor,
        connect_vbms_path="/Users/alex_gaynor/projects/va/connect_vbms/",
        endpoint_url="https://filenet.test.vbms.aide.oit.va.gov/vbmsp2-cms/streaming/eDocumentService-v4",
        keyfile="/Users/alex_gaynor/projects/va/vbms-credentials/test/client3.jks",
        samlfile="/Users/alex_gaynor/projects/va/vbms-credentials/test/samlToken-cui-tst.xml",
        key=None,
    )
    reactor.listenTCP(8080, Site(app.app.resource()), interface="localhost")
    return Deferred()


if __name__ == "__main__":
    react(main, sys.argv[1:])
