from twisted.web import resource


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
