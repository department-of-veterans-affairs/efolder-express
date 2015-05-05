import io
import os
import stat
import sys
import tempfile
import zipfile

import jinja2

import klein

from pathlib import Path

from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.internet.task import react
from twisted.internet.utils import getProcessOutput
from twisted.web.server import Site


class DownloadEFolder(object):
    app = klein.Klein()

    def __init__(self, reactor):
        self.reactor = reactor

        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                str(Path(__file__).parent.joinpath("templates")),
            ),
            autoescape=True
        )

    def render_template(self, template_name):
        t = self.jinja_env.get_template(template_name)
        return t.render({})

    def _execute_connect_vbms(self, request, formatter):
        ruby_code = """#!/usr/bin/env ruby

require '/Users/alex_gaynor/projects/va/connect_vbms/src/vbms.rb'

client = VBMS::Client.new(
    "https://filenet.test.vbms.aide.oit.va.gov/vbmsp2-cms/streaming/eDocumentService-v4",
    "/Users/alex_gaynor/projects/va/vbms-credentials/test/client3.jks",
    "/Users/alex_gaynor/projects/va/vbms-credentials/test/samlToken-cui-tst.xml",
    nil,
    "importkey",
    nil,
    nil,
)
request = {request}
result = client.send(request)
STDOUT.write({formatter})
        """.format(request=request, formatter=formatter).strip()
        with tempfile.NamedTemporaryFile(suffix=".rb", delete=False) as f:
            f.write(ruby_code)

        st = os.stat(f.name)
        os.chmod(f.name, st.st_mode | stat.S_IEXEC)

        return getProcessOutput(
            "/Users/alex_gaynor/.gem/ruby/2.0.0/bin/bundle",
            ["exec", f.name],
            env=os.environ,
            path="/Users/alex_gaynor/projects/va/connect_vbms/",
            reactor=self.reactor
        )

    @app.route("/")
    def index(self, request):
        return self.render_template("index.html")

    @app.route("/download/", methods=["POST"])
    @inlineCallbacks
    def download(self, request):
        file_number = request.args["file_number"][0]
        data = io.BytesIO()

        files = (yield self._execute_connect_vbms(
            "VBMS::Requests::ListDocuments.new({!r})".format(file_number),
            'result.map(&:document_id).join("\\n")'
        )).splitlines()
        with zipfile.ZipFile(data, "w") as zip_file:
            for i, f in enumerate(files):
                contents = yield self._execute_connect_vbms(
                    "VBMS::Requests::FetchDocumentById.new({!r})".format(f),
                    "result.content",
                )
                zip_file.writestr(
                    "{}-eFolder/{}".format(file_number, i), contents
                )
        request.setHeader("Content-Type", "application/zip")
        returnValue(data.getvalue())


def main(reactor):
    app = DownloadEFolder(reactor)
    reactor.listenTCP(8080, Site(app.app.resource()), interface="localhost")
    return Deferred()


if __name__ == "__main__":
    react(main, sys.argv[1:])
