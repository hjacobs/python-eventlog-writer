#!/usr/bin/env python
# -*- coding: utf-8 -*-

__all__ = ['log', 'register', 'register_all', 'Event']

from collections import namedtuple
from cloghandler import ConcurrentRotatingFileHandler
from tcloghandler import ConcurrentTimeRotatingFileHandler

import logging
import logging.handlers
import os
import re
import string

# START Default behaviour of the module: if need to change these, do it immediately after module import
filesize_rotation = False
rotation_maxBytes = 5242880
rotation_backupCount = 9
rotation_when = 'midnight'
# END

event_log = None
event_log_layout = None
event_types = {}
field_pattern = re.compile('^[a-z][a-zA-Z0-9]*$')
name_pattern = re.compile(r'^[A-Z0-9]+(:?_?[A-Z0-9])*$')

Event = namedtuple('Event', ['id', 'fields'])


class EscapeFormatter(string.Formatter):

    def convert_field(self, value, conversion):
        value = (value.encode(encoding='utf-8') if isinstance(value, unicode) else value)
        if conversion == 'e':
            return ('null' if value is None else str(value).replace('\t', '\\t').replace('\n', '\\n'))
        return super(EscapeFormatter, self).convert_field(value, conversion)


formatter = EscapeFormatter()


class EventlogError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


def _init(log_handler=None, layout_handler=None, path=None):
    ''' Initializes eventlog and layout. Called only once after initial call to register or log. Optional handlers are
    used only by unit tests to swap file for stream handlers. '''

    global event_log, event_log_layout

    # Take the path passed as a parameter or use APP_HOME if present, otherwise fallback to current directory.
    path = path or ((os.environ['APP_HOME'] + '/logs/' if 'APP_HOME' in os.environ else './'))
    event_log = logging.getLogger('eventlog')
    # prevent logging event log stuff to STDOUT (root logger):
    event_log.propagate = False
    event_log.setLevel(logging.INFO)
    if filesize_rotation:
        event_log_file_handler = ConcurrentRotatingFileHandler(os.path.join(path, 'eventlog.log'),
                backupCount=rotation_backupCount, maxBytes=rotation_maxBytes)
    else:
        event_log_file_handler = ConcurrentTimeRotatingFileHandler(os.path.join(path, 'eventlog.log'),
                when=rotation_when)
    event_log_file_handler.setLevel(logging.INFO)

    event_log_layout = logging.getLogger('eventlog-layout')
    event_log_layout.propagate = False
    event_log_layout.setLevel(logging.INFO)
    if filesize_rotation:
        event_layout_file_handler = ConcurrentRotatingFileHandler(os.path.join(path, 'eventlog.layout'),
                backupCount=rotation_backupCount, maxBytes=rotation_maxBytes)
    else:
        event_layout_file_handler = ConcurrentTimeRotatingFileHandler(os.path.join(path, 'eventlog.layout'),
                when=rotation_when)
    event_layout_file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s %(message)s')

    event_log_file_handler.setFormatter(formatter)
    event_layout_file_handler.setFormatter(formatter)

    if log_handler:
        log_handler.setFormatter(formatter)
    if layout_handler:
        layout_handler.setFormatter(formatter)

    event_log.addHandler((event_log_file_handler if log_handler is None else log_handler))
    event_log_layout.addHandler((event_layout_file_handler if layout_handler is None else layout_handler))


def register(e_id, name, *args):
    ''' Registers new event type. Important: order of events matters, later the events will be logged in the order
    provided in register function. Example:
        register(0x62001, 'SOME_PAYMENT', 'first', 'second', 'third')
        # or if we keep events in a data structure for later use/reuse
        events = ['first', 'second', 'third']
        register(0x62001, 'SOME_PAYMENT', *events)
    '''

    global event_log, event_log_layout
    if event_log is None or event_log_layout is None:
        _init()

    if not isinstance(e_id, int):
        raise EventlogError('Invalid or missing event id')
    if not name_pattern.match(name):
        raise EventlogError('Event names must be UPPERCASE_WITH_UNDERSCORES')
    if e_id in event_types:
        raise EventlogError('Event with id {0!s} is already registered'.format(e_id))
    if not all(map(field_pattern.match, args)):
        raise EventlogError('Event field names must be camel case with first letter lower case')

    event_log_layout.info('{0:x}\t{1!s}'.format(e_id, name) + ''.join('\t{}' for i in range(len(args))).format(*args))
    event_types[e_id] = args


def register_all(events, path=None):
    ''' Registers a dict of events. The dict must contain event names as keys and Event objects as values. All event
    names must be written in upper case. The optional path parameter tells eventlog where to write log files. Example:
        register_all({
            'PAYMENT_RECEIVED': Event(0x62001, ['userName', 'amout']),
            'PAYMENT_CANCELLED': Event(0x62002, ['userName', 'reason'])
        })
    '''

    if event_log is None or event_log_layout is None:
        _init(path=path)

    for name, event in events.items():
        register(event.id, name, *event.fields)


def log(e_id, **kwargs):
    ''' Logs events with given id. The order of keyword arguments will be determined by the order set while registering
    given event type. In other words, it doesn't matter here. Example:
        log(0x62001, first='PAYMENT', third='DE', second=23.4)
        # or if we keep events in a data structure for later use/reuse
        events = { 'first': 'PAYMENT', 'third': 'DE', 'second': 23.4 }
        log(0x62001, **events)
    '''

    global event_log, event_log_layout

    if event_log is None or event_log_layout is None:
        _init()

    # flow id placeholder
    flow_id = ' '
    if e_id in event_types:
        # filter out event types that were registered, but are not in keyword args, then escape tabs and newlines
        event_log.info('{1} {0:x}'.format(e_id, flow_id) + formatter.format(''.join('\t{' + k + '!e}' for k in
                       filter(lambda e: e in kwargs, event_types[e_id])), **kwargs))
    else:
        raise EventlogError('Event with id {0!s} is not registered. Did you forget to call register?'.format(e_id))


if __name__ == '__main__':
    # test run
    EVENTS = {'TEST_EVENT1': Event(0xffff1, ['test', 'anotherAttribute']), 'TEST_EVENT2': Event(0x77ff2, ['test',
              'oneMoreField'])}
    logging.basicConfig(level=logging.INFO)
    logging.info('Testing event logging..')
    register_all(EVENTS)
    log(EVENTS['TEST_EVENT1'].id, test='test', anotherAttribute='avalue')
    log(EVENTS['TEST_EVENT2'].id, test='test', oneMoreField='fvalue')
    logging.info('..done (see eventlog.log)')
