#!/usr/bin/env python
# -*- coding: utf-8 -*-

import inspect
import os
from setuptools import setup

__location__ = os.path.join(os.getcwd(), os.path.dirname(inspect.getfile(inspect.currentframe())))

# Add here all kinds of additional classifiers as defined under
# https://pypi.python.org/pypi?%3Aaction=list_classifiers
CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'License :: OSI Approved :: Apache Software License',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3.3',
    'Programming Language :: Python :: 3.4',
]


def read(fname):
    return open(os.path.join(__location__, fname)).read()


def get_install_requirements(path):
    content = open(os.path.join(__location__, path)).read()
    return [req for req in content.split('\\n') if req != '']


install_reqs = get_install_requirements('requirements.txt')

setup(name='eventlog-writer',
      version='0.4.5',
      author='Henning Jacobs',
      author_email='henning.jacobs@zalando.de',
      description='Python module to write business events',
      url='https://github.com/zalando/python-eventlog-writer',
      py_modules=['eventlog', 'tcloghandler'],
      long_description=read('README.rst'),
      classifiers=CLASSIFIERS,
      install_requires=install_reqs
      )
