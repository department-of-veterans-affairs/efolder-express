import io
import os
import stat
import subprocess
import tempfile
import zipfile

import jinja2

import klein

from pathlib import Path


class DownloadEFolder(object):
    app = klein.Klein()

    def __init__(self):
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

        return subprocess.check_output([
            "/Users/alex_gaynor/.gem/ruby/2.0.0/bin/bundle",
            "exec",
            f.name
        ], cwd="/Users/alex_gaynor/projects/va/connect_vbms/")

    @app.route("/")
    def index(self, request):
        return self.render_template("index.html")

    @app.route("/download/", methods=["POST"])
    def download(self, request):
        file_number = request.args["file_number"][0]
        data = io.BytesIO()

        files = self._execute_connect_vbms(
            "VBMS::Requests::ListDocuments.new({!r})".format(file_number),
            'result.join("\\n")'
        ).splitlines()
        with zipfile.ZipFile(data, "w") as zip_file:
            for i, f in enumerate(files):
                contents = self._execute_connect_vbms(
                    "VBMS::Requests::FetchDocumentById.new({!r})".format(f),
                    "result",
                )
                zip_file.writestr("{}-eFolder/{}".format(file_number, i), contents)
        request.setHeader("Content-Type", "application/zip")
        return data.getvalue()



if __name__ == "__main__":
    DownloadEFolder().app.run("localhost", 8080)
