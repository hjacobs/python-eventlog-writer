#!/usr/bin/env python
# -*- coding: utf-8 -*-

__all__ = ['register', 'log']

import logging
import logging.handlers
import os
import re
import string

event_log = None
event_log_layout = None
event_types = {}
field_pattern = re.compile('^[a-z][a-zA-Z0-9]*$')
name_pattern = re.compile(r'^[A-Z0-9]+(:?_?[A-Z0-9])*$')


class EscapeFormatter(string.Formatter):

    def convert_field(self, value, conversion):
        if conversion == 'e':
            return ('null' if value is None else str(value).replace('\t', '\\t').replace('\n', '\\n'))
        return super(EscapeFormatter, self).convert_field(value, conversion)


formatter = EscapeFormatter()


class EventlogError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


def _init(log_handler=None, layout_handler=None):
    ''' Initializes eventlog and layout. Called only once after initial call to register or log. Optional handlers are
    used only by unit tests to swap file for stream handlers. '''

    global event_log, event_log_layout

    path = (os.environ['APP_HOME'] + '/logs/' if 'APP_HOME' in os.environ else './')

    event_log = logging.getLogger('eventlog')
    event_log.setLevel(logging.INFO)
    event_log_file_handler = logging.handlers.TimedRotatingFileHandler(path + 'eventlog.log', when='midnight')
    event_log_file_handler.setLevel(logging.INFO)

    event_log_layout = logging.getLogger('eventlog-layout')
    event_log_layout.setLevel(logging.INFO)
    event_layout_file_handler = logging.handlers.TimedRotatingFileHandler(path + 'eventlog.layout', when='midnight')
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


def log(e_id, **kwargs):
    ''' Logs events with given id. The order of keyword arguments will be determined by the order set while registering
    given event type. In other words, it doesn't matter here. Example:
        log(0x62001, first='PAYMENT', third='DE', second=23.4)
        # or if we keep events in a data structure for later use/reuse
        events = { 'first': 'PAYMENT', 'third': 'DE', 'second': 23.4 }
        log(0x62001, **events)
    '''

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


