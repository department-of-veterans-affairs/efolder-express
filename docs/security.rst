Security
========

Authentication and Authorization
--------------------------------

**Work in progress**

eFolder Express does not currently authenticate users. We are working with the
VA SSO team to requires all users to authenticate with the VA SSO. Once we
have authentication, we will also require users have a particularly ACL in
order to use eFolder Express.

Confidentiality
---------------

While building the ``.zip`` file, eFolder Express temporarily stores files
from the eFolder on disk. These files are encrypted using FIPS 140-2
cryptography: AES-128 in CBC mode with HMAC-SHA256 for authentication in an
encrypt-then-MAC composition.

Auditing
--------

All requests to access an eFolder are logged by the server, every request to
VBMS's API is logged, as is every time an eFolder is downloaded.
