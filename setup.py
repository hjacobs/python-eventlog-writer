#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup
import argparse
import nose
import os

parser = argparse.ArgumentParser(description='RQM tool to report and display test and environment related information')

group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('-t', '--test', action='store_true', help='Runs tests')
# To this group install / deploy actions should be added

args = parser.parse_args()

if args.test:
    argv = ['nosetests']
    argv.append('--with-coverage')
    argv.append('--cover-xml')
    argv.append('--with-doctest')
    argv.append('--cover-xml-file=' + os.getcwd() + '/coverage.xml')
    argv.append('--with-xunit')
    argv.append('--xunit-file=' + os.getcwd() + '/nosetests.xml')
    nose.run(argv=argv)
else:
    setup(name='zalando-eventlog', version='0.3', py_modules=['eventlog'])
