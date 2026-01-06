==========
acasclient
==========


.. image:: https://img.shields.io/pypi/v/acasclient.svg
        :target: https://pypi.python.org/pypi/acasclient

.. image:: https://img.shields.io/travis/mcneilco/acasclient.svg
        :target: https://travis-ci.org/mcneilco/acasclient

.. image:: https://readthedocs.org/projects/acasclient/badge/?version=latest
        :target: https://acasclient.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status




ACAS API Client


* Free software: GNU General Public License v3
* Documentation: https://acasclient.readthedocs.io.


Releases
--------
To publish a new release of acasclient, run:
```
        export NEW_VERSION=X.Y.Z
        bump2version part --new-version $NEW_VERSION
        git tag $NEW_VERSION
        git push origin tag $NEW_VERSION
```
This will trigger a CI build that will publish the new version to PyPI if all tests pass.

Features
--------

* TODO

Credits
-------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage


Installation
------------
pip install acasclient