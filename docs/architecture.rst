Architecture
============

eFolder Express is written in Python, using the Twisted evented networking
framework. The application handles HTTPS termination in-process.

A relational database is used for storing metadata about in-process eFolder
downloads.

Local disk is used for storing encrypted documents while a download is in
progress (see :doc:`/security` for more details).
