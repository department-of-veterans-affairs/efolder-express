import datetime
import tempfile
import uuid
import zipfile

import alchimia

import sqlalchemy

from twisted.internet.defer import inlineCallbacks, returnValue


class DownloadNotFound(Exception):
    def __init__(self, request_id):
        super(DownloadNotFound, self).__init__(request_id)
        self.request_id = request_id


class DownloadStatus(object):
    def __init__(self, request_id, file_number, state, documents):
        self.request_id = request_id
        self.file_number = file_number
        self.state = state
        self.documents = documents

    @property
    def completed(self):
        return (
            self.documents and
            all(doc.content_location or doc.errored for doc in self.documents)
        )

    @property
    def percent_completed(self):
        if not self.documents:
            return 5

        completed = sum(
            1 for doc in self.documents if doc.content_location or doc.errored
        )
        return int(100 * (completed / float(len(self.documents))))

    def build_zip(self, jinja_env, fernet, document_types):
        with zipfile.ZipFile(
            tempfile.NamedTemporaryFile(suffix=".zip", delete=False),
            "w",
            compression=zipfile.ZIP_DEFLATED
        ) as z:
            for doc in self.documents:
                if doc.content_location:
                    with open(doc.content_location) as f:
                        data = fernet.decrypt(f.read())
                    z.writestr(
                        "{}-eFolder/{}".format(self.file_number, doc.filename),
                        data,
                    )

            readme_template = jinja_env.get_template("readme.txt")
            z.writestr(
                "{}-eFolder/README.txt".format(self.file_number),
                readme_template.render({
                    "status": self,
                    "document_types": document_types,
                }).encode(),
            )
        return z.filename


class Document(object):
    def __init__(self, id, download_id, document_id, doc_type, filename,
                 received_at, source, content_location, errored):
        self.id = id
        self.download_id = download_id
        self.document_id = document_id
        self.doc_type = doc_type
        self.filename = filename
        self.received_at = received_at
        self.source = source
        self.content_location = content_location
        self.errored = errored

    @classmethod
    def from_json(cls, download_id, data):
        return cls(
            str(uuid.uuid4()),
            download_id,
            data["document_id"],
            data["doc_type"],
            data["filename"],
            datetime.datetime.strptime(data["received_at"], "%Y-%m-%d").date(),
            data["source"],
            content_location=None,
            errored=False,
        )


class DownloadDatabase(object):
    def __init__(self, reactor, thread_pool, database_uri):
        self._engine = sqlalchemy.create_engine(
            database_uri,
            strategy=alchimia.TWISTED_STRATEGY,
            reactor=reactor,
            thread_pool=thread_pool,
        )

        self._metadata = sqlalchemy.MetaData()

        self._downloads = sqlalchemy.Table(
            "downloads",
            self._metadata,
            sqlalchemy.Column(
                "request_id",
                sqlalchemy.Text(),
                primary_key=True,
                nullable=False,
            ),
            sqlalchemy.Column(
                "file_number",
                sqlalchemy.Text(),
                nullable=False,
            ),
            sqlalchemy.Column(
                "started_at",
                sqlalchemy.DateTime(),
                nullable=False,
            ),
            sqlalchemy.Column(
                "state",
                sqlalchemy.Enum(
                    "STARTED",
                    "MANIFEST_DOWNLOADED",
                    "ERRORED",
                ),
                nullable=False,
            ),
        )

        self._documents = sqlalchemy.Table(
            "documents",
            self._metadata,
            sqlalchemy.Column(
                "id",
                sqlalchemy.Text(),
                primary_key=True,
                nullable=False,
            ),
            sqlalchemy.Column(
                "download_id",
                sqlalchemy.Text(),
                sqlalchemy.ForeignKey("downloads.request_id"),
                nullable=False,
            ),
            sqlalchemy.Column(
                "document_id",
                sqlalchemy.Text(),
                nullable=False,
            ),
            sqlalchemy.Column(
                "doc_type",
                sqlalchemy.Text(),
                nullable=False,
            ),
            sqlalchemy.Column(
                "filename",
                sqlalchemy.Text(),
                nullable=False,
            ),
            sqlalchemy.Column(
                "received_at",
                sqlalchemy.Date(),
                nullable=False,
            ),
            sqlalchemy.Column(
                "source",
                sqlalchemy.Text(),
                nullable=True,
            ),
            sqlalchemy.Column(
                "content_location",
                sqlalchemy.Text(),
                nullable=True,
            ),
            sqlalchemy.Column(
                "errored",
                sqlalchemy.Boolean(),
                nullable=False,
            ),
        )

    def _document_from_row(self, row):
        return Document(
            id=row[self._documents.c.id],
            download_id=row[self._documents.c.download_id],
            document_id=row[self._documents.c.document_id],
            doc_type=row[self._documents.c.doc_type],
            filename=row[self._documents.c.filename],
            received_at=row[self._documents.c.received_at],
            source=row[self._documents.c.source],
            content_location=row[self._documents.c.content_location],
            errored=row[self._documents.c.errored],
        )

    def create_download(self, request_id, file_number):
        return self._engine.execute(self._downloads.insert().values(
            request_id=request_id,
            file_number=file_number,
            started_at=datetime.datetime.utcnow(),
            state="STARTED",
        ))

    def mark_download_errored(self, request_id):
        return self._engine.execute(self._downloads.update().where(
            self._downloads.c.request_id == request_id
        ).values(state="ERRORED"))

    def create_documents(self, documents):
        return self._engine.execute(self._documents.insert(), [
            {
                "id": doc.id,
                "download_id": doc.download_id,
                "document_id": doc.document_id,
                "doc_type": doc.doc_type,
                "filename": doc.filename,
                "received_at": doc.received_at,
                "source": doc.source,
                "content_location": None,
                "errored": False
            }
            for doc in documents
        ])

    def mark_document_errored(self, document):
        return self._engine.execute(self._documents.update().where(
            self._documents.c.id == document.id
        ).values(errored=True))

    def set_document_content_location(self, document, path):
        return self._engine.execute(self._documents.update().where(
            self._documents.c.id == document.id,
        ).values(
            content_location=path,
        ))

    @inlineCallbacks
    def get_download(self, request_id):
        query = self._downloads.select().where(
            self._downloads.c.request_id == request_id
        )
        download_row = (yield (yield self._engine.execute(query)).first())
        if download_row is None:
            raise DownloadNotFound(request_id)

        query = self._documents.select().where(
            self._documents.c.download_id == request_id,
        )
        document_rows = yield self._engine.execute(query)

        returnValue(DownloadStatus(
            request_id=download_row[self._downloads.c.request_id],
            file_number=download_row[self._downloads.c.file_number],
            state=download_row[self._downloads.c.state],
            documents=[
                self._document_from_row(row)
                for row in (yield document_rows.fetchall())
            ]
        ))
