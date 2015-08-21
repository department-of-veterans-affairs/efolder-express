Installation
============

You'll need to have Python 2.7 and `virtualenv`_ installed, as well as a
``virtualenv`` created for this application. Once you have that, install the
dependencies:

.. code-block:: console

    $ pip install -r requirements.txt

Full environment
----------------

These instructions will guide you through setting up a complete development
environment. If you only want to work on the frontend you can skip down the demo
environment instructions.

You'll need to download and build `connect_vbms`_.

Now create a configuration file, in the same vein as ``config/test.yml``.

Next, create the database:

.. code-block:: console

    $ twistd -no efolder-express --config=path/to/config.yml create-database

Finally, run the server:

.. code-block:: console

    $ twistd -no efolder-express --config=path/to/config.yml

And open up your browser to ``http://locahost:8080``.

Demo environment
----------------

Everything is installed, you can now test efolder-express out. Start it up by
running:

.. code-block:: console

    $ twistd -no efolder-express --demo

You can visit the following URLs to test it out:

* ``http://127.0.0.1:8080/efolder-express/``: The index page.
* ``http://127.0.0.1:8080/efolder-express/download/started/``: A download that
  has just started, it is still fetching the manifest of files.
* ``http://127.0.0.1:8080/efolder-express/download/manifest-download-error/``:
  A download that hit an error fetching the manifest.
* ``http://127.0.0.1:8080/efolder-express/download/manifest-downloaded/``: A
  download which completed fetching the manifest, and has 1 in-progress file.
* ``http://127.0.0.1:8080/efolder-express/download/download-in-progress/``: A
  download which completed fetching the manifest, and has 3 files: 1
  in-progress, 1 succeeded, and 1 errored.
* ``http://127.0.0.1:8080/efolder-express/download/completed/``: A download
  which is completed, there are 3 files.

Testing
-------

To run the tests, first install the additional test dependencies:

.. code-block:: console

    $ pip install -r test-requirements.txt

Then run:

.. code-block:: console

    $ py.test tests/

and you'll see passing tests.

.. _`virtualenv`: https://packaging.python.org/en/latest/installing.html#requirements-for-installing-packages
.. _`connect_vbms`: https://github.com/department-of-veterans-affairs/connect_vbms
