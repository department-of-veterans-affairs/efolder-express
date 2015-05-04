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

    @app.route("/")
    def index(self, request):
        return self.render_template("index.html")


if __name__ == "__main__":
    DownloadEFolder().app.run("localhost", 8080)
