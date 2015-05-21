from twisted.web import resource, server


class ForceHTTPSResource(resource.Resource):
    isLeaf = True

    def __init__(self, target_netloc):
        self._target_netloc = target_netloc
        resource.Resource.__init__(self)

    def getChild(self, name, request):
        return self

    def render(self, request):
        path = request.URLPath()
        path.scheme = "https"
        path.netloc = self._target_netloc

        request.redirect(str(path))
        request.finish()
        return server.NOT_DONE_YET


class HSTSResource(resource.Resource):
    def __init__(self, wrapped):
        resource.Resource.__init__(self)
        self._wrapped = wrapped

    @property
    def isLeaf(self):
        return self._wrapped.isLeaf

    def render(self, request):
        request.responseHeaders.addRawHeader(
            'Strict-Transport-Security',
            'max-age=31536000; includeSubDomains'
        )
        return self._wrapped.render(request)
