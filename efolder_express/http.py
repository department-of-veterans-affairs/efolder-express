from twisted.internet.defer import succeed
from twisted.web import resource, server


class ForceHTTPSResource(resource.Resource):
    isLeaf = True

    def getChild(self, name, request):
        return self

    def render(self, request):
        path = request.URLPath()
        path.scheme = "https"
        # TODO: in production the netloc shouldn't change
        path.netloc = "localhost:8081"

        request.redirect(str(path))
        request.finish()
        return server.NOT_DONE_YET
