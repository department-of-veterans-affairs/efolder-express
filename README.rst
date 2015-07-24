eFolder Express
===============

This is a small application to facilitate downloading the entire eFolder from
VBMS as a single .zip file.

This application is written in Python, using Twisted, and requires you have
``connect_vbms`` setup on your machine. Create a configuration file, in YAML,
in the style of ``config/test.yml``, and then this app can be run as:

.. code-block:: console

    $ twistd -no efolder-express --config=config/test.yml

Known places this will be useful
--------------------------------

These are known places where currently, VA employees download documents from the
eFolder one file at a time:

* FOIA requests from Veterans for their files
* Attorneys at the Office of the General Counsel who download eFolders all day
* Contract examiners for disability exams