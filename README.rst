===============
EventLog Writer
===============

Installation
============

.. code-block:: bash

    $ sudo pip install eventlog-writer


Usage
=====

.. code-block:: python

    import eventlog
    eventlog.register(0x123ab, 'SOME_EVENT', 'first', 'second', 'third')
    eventlog.log(0x123ab, first='a', second=123, third='foobar')
