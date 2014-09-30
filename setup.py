#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

setup(name='zalando-eventlog', version='0.4.5', py_modules=['eventlog', 'tcloghandler'],
      install_requires=['ConcurrentLogHandler'])
