import json
import os
import stat
import tempfile

from twisted.internet.defer import (
    DeferredSemaphore, inlineCallbacks, returnValue
)
from twisted.internet.utils import getProcessOutputAndValue


class VBMSError(Exception):
    def __init__(self, stdout, stderr, exit_code):
        super(VBMSError, self).__init__(stderr)
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


class VBMSClient(object):
    def __init__(self, reactor, connect_vbms_path, bundle_path, endpoint_url,
                 keyfile, samlfile, key, keypass, ca_cert, client_cert):
        self._reactor = reactor

        self._connect_vbms_path = connect_vbms_path
        self._bundle_path = bundle_path
        self._endpoint_url = endpoint_url
        self._keyfile = keyfile
        self._samlfile = samlfile
        self._key = key
        self._keypass = keypass
        self._ca_cert = ca_cert
        self._client_cert = client_cert

        self._connect_vbms_semaphore = DeferredSemaphore(tokens=8)

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
                stdout, stderr, exit_code = yield getProcessOutputAndValue(
                    '/bin/bash', [
                        '-lc',
                        '{} exec {} {}'.format(
                            self._bundle_path,
                            f.name,
                            " ".join(map(pipes.quote, args))
                        )
                    ]
                    env=os.environ,
                    path=self._connect_vbms_path,
                    reactor=self._reactor
                )
            finally:
                timer.stop()
            if exit_code != 0:
                raise VBMSError(stdout, stderr, exit_code)
            returnValue(stdout)

        return self._connect_vbms_semaphore.run(run)

    @inlineCallbacks
    def get_document_types(self, logger):
        response = yield self._execute_connect_vbms(
            logger.bind(process="GetDocumentTypes"),
            "VBMS::Requests::GetDocumentTypes.new()",
            "result.map(&:to_h).to_json",
            [],
        )
        returnValue(json.loads(response))

    @inlineCallbacks
    def list_documents(self, logger, file_number):
        response = yield self._execute_connect_vbms(
            logger.bind(process="ListDocuments"),
            "VBMS::Requests::ListDocuments.new(ARGV[0])",
            'result.map(&:to_h).to_json',
            [file_number],
        )
        returnValue(json.loads(response))

    def fetch_document_contents(self, logger, document_id):
        return self._execute_connect_vbms(
            logger.bind(process="FetchDocumentById"),
            "VBMS::Requests::FetchDocumentById.new(ARGV[0])",
            "result.content",
            [document_id],
        )
