#!/usr/bin/python
# -*- coding: utf-8 -*-

import cStringIO
import unittest
from eventlog import EventlogError, _init, log, register
from logging import StreamHandler
from re import split


class TestEventlog(unittest.TestCase):

    def test_register_invalid_id(self):
        with self.assertRaises(EventlogError):
            register('id', 'NAME')

    def test_register_invalid_name(self):
        with self.assertRaises(EventlogError):
            register(1, 'EVENT__NAME')
        with self.assertRaises(EventlogError):
            register(1, 'event_name')

    def test_register_invalid_event(self):
        with self.assertRaises(EventlogError):
            register(1, 'EVENT_NAME', 'not_camel_case')

    def test_register_id_twice(self):
        register(1, 'EVENT_NAME', 'valid', 'alsoValid')
        with self.assertRaises(EventlogError):
            register(1, 'EVENT_NAME', 'valid', 'alsoValid')

    def test_log_unregistered_id(self):
        with self.assertRaises(EventlogError):
            log(1, param='test')

    def test_log_format(self):
        e_id = 12345
        log_stream = cStringIO.StringIO()
        layout_stream = cStringIO.StringIO()
        log_handler = StreamHandler(log_stream)
        layout_handler = StreamHandler(layout_stream)
        _init(log_handler, layout_handler)

        register(e_id, 'EVENT_NAME', 'valid', 'key')
        log(e_id, key=2, valid='first')

        layout = split('\s+', layout_stream.getvalue().strip())
        eventlog = split('\s+', log_stream.getvalue().strip())

        self.assertEqual('{0:x}'.format(e_id), layout[2], 'Should have hex id in layout')
        self.assertEqual('{0:x}'.format(e_id), eventlog[2], 'Should have hex id in eventlog')
        self.assertEquals('first', eventlog[3], 'Should maintain registered order (1)')
        self.assertEquals('2', eventlog[4], 'Should maintain registered order (2)')

    def test_less_arguments(self):
        e_id = 12346
        log_stream = cStringIO.StringIO()
        layout_stream = cStringIO.StringIO()
        log_handler = StreamHandler(log_stream)
        layout_handler = StreamHandler(layout_stream)
        _init(log_handler, layout_handler)

        register(e_id, 'EVENT_NAME', 'valid', 'key', 'last')
        log(e_id, key='second')

        layout = split('\s+', layout_stream.getvalue().strip())
        eventlog = split('\s+', log_stream.getvalue().strip())

        self.assertEquals('valid', layout[4], 'Should have valid layout (1)')
        self.assertEquals('key', layout[5], 'Should have valid layout (2)')
        self.assertEquals('last', layout[6], 'Should have valid layout (3)')
        self.assertEquals(4, len(eventlog), 'Should have only four entries')
        self.assertEquals('second', eventlog[3], 'Should have only one value')

        log(e_id, last='end', valid='start')
        eventlog = split('\s+', log_stream.getvalue().split('\n')[1].strip())

        self.assertEquals(5, len(eventlog), 'Should have only five entries')
        self.assertEquals('start', eventlog[3], 'Should maintain order with less arguments (1)')
        self.assertEquals('end', eventlog[4], 'Should maintain order with less arguments (2)')

    def test_tabs_and_newlines(self):
        e_id = 12347
        log_stream = cStringIO.StringIO()
        layout_stream = cStringIO.StringIO()
        log_handler = StreamHandler(log_stream)
        layout_handler = StreamHandler(layout_stream)
        _init(log_handler, layout_handler)

        register(e_id, 'EVENT_NAME', 'key')
        log(e_id, key='contains\ttab')

        eventlog = split('\s+', log_stream.getvalue().strip())

        self.assertEquals(4, len(eventlog), 'Should have only four entries')
        self.assertEquals('contains\\ttab', eventlog[3], 'Should have only one value (1)')

        log(e_id, key='contains\nnewline')

        eventlog = split('\s+', log_stream.getvalue().split('\n')[1].strip())

        self.assertEquals('contains\\nnewline', eventlog[3], 'Should have only one value (2)')

    def test_none_values(self):
        e_id = 12348
        log_stream = cStringIO.StringIO()
        layout_stream = cStringIO.StringIO()
        log_handler = StreamHandler(log_stream)
        layout_handler = StreamHandler(layout_stream)
        _init(log_handler, layout_handler)

        register(e_id, 'EVENT_NAME', 'key')
        log(e_id, key=None)

        eventlog = split('\s+', log_stream.getvalue().strip())

        self.assertEquals(4, len(eventlog), 'Should have only four entries')
        self.assertEquals('null', eventlog[3], 'Should convert None to null')


if __name__ == '__main__':
    unittest.main()
