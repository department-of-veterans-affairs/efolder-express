Installation
============

You'll need to have Python 2.7 and ``virtualenv`` installed, as well as a
``virtualenv`` for this application. Once you have that, install the
dependencies:

.. code-block:: console

    $ pip install -r requirements.txt

Now create a configuration file, in the same vein as ``config/test.yml``, in
development you can use the X.509 TLS certificate, private key, and DH
parameters found in ``dev/``.

Finally, run the server:

.. code-block:: console

    $ twistd -no efolder-express --config=path/to/config.yml

And open up your browser to ``http://locahost:8080``.

Testing
-------

To run the tests, first install the additional test dependencies:

.. code-block:: console

    $ pip install -r test-requirements.txt

Then run:

.. code-block:: console

    $ py.test

and you'll see passing tests.
