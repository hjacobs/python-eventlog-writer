#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module provide log handler ConcurrentTimeRotatingFileHandler. We do this by extending the implementation of
ConcurrentLogHandler 0.9.1 to support Time Based rotations (like stdlib TimedRotatingFileHandler)
See: https://pypi.python.org/pypi/ConcurrentLogHandler/0.9.1

"""

from __future__ import print_function

import os
import sys
import re
import time
from random import randint
from logging import Handler, LogRecord
from logging.handlers import BaseRotatingHandler

from stat import ST_MTIME

#
# Some constants...
#

_MIDNIGHT = 24 * 60 * 60  # number of seconds in a day

try:
    import codecs
except ImportError:
    codecs = None

# sibling module than handles all the ugly platform-specific details of file locking
from portalocker import lock, unlock, LOCK_EX  # , LOCK_NB, LockException


# Workaround for handleError() in Python 2.7+ where record is written to stderr

class NullLogRecord(LogRecord):

    def __init__(self):
        pass

    def __getattr__(self, attr):
        return None


class ConcurrentTimeRotatingFileHandler(BaseRotatingHandler):

    """
    Handler for logging to a set of files, which switches from one file to the
    next when the current file reaches a certain size. Multiple processes can
    write to the log file concurrently, but this may mean that the file will
    exceed the given size.
    """

    def __init__(
        self,
        filename,
        when='h',
        interval=1,
        backupCount=0,
        encoding=None,
        utc=False,
        mode='a',
        debug=True,
        delay=0,
    ):
        """
        Open the specified file and use it as the stream for logging.

        By default, the file grows indefinitely. You can specify particular
        values of maxBytes and backupCount to allow the file to rollover at
        a predetermined size.

        Rollover occurs whenever the current log file is nearly maxBytes in
        length. If backupCount is >= 1, the system will successively create
        new files with the same pathname as the base file, but with extensions
        ".1", ".2" etc. appended to it. For example, with a backupCount of 5
        and a base file name of "app.log", you would get "app.log",
        "app.log.1", "app.log.2", ... through to "app.log.5". The file being
        written to is always "app.log" - when it gets filled up, it is closed
        and renamed to "app.log.1", and if files "app.log.1", "app.log.2" etc.
        exist, then they are renamed to "app.log.2", "app.log.3" etc.
        respectively.

        If maxBytes is zero, rollover never occurs.

        On Windows, it is not possible to rename a file that is currently opened
        by another process.  This means that it is not possible to rotate the
        log files if multiple processes is using the same log file.  In this
        case, the current log file will continue to grow until the rotation can
        be completed successfully.  In order for rotation to be possible, all of
        the other processes need to close the file first.  A mechanism, called
        "degraded" mode, has been created for this scenario.  In degraded mode,
        the log file is closed after each log message is written.  So once all
        processes have entered degraded mode, the net rotation attempt should
        be successful and then normal logging can be resumed.  Using the 'delay'
        parameter may help reduce contention in some usage patterns.

        This log handler assumes that all concurrent processes logging to a
        single file will are using only this class, and that the exact same
        parameters are provided to each instance of this class.  If, for
        example, two different processes are using this class, but with
        different values for 'maxBytes' or 'backupCount', then odd behavior is
        expected. The same is true if this class is used by one application, but
        the RotatingFileHandler is used by another.
        """

                       # filename, mode='a', maxBytes=0, backupCount=0, encoding=None, debug=True, delay=0):
        # Absolute file name handling done by FileHandler since Python 2.5
        BaseRotatingHandler.__init__(self, filename, mode, encoding, delay)

        self.when = when.upper()
        self.backupCount = backupCount
        self.utc = utc
        # Calculate the real rollover interval, which is just the number of
        # seconds between rollovers.  Also set the filename suffix used when
        # a rollover occurs.  Current 'when' events supported:
        # S - Seconds
        # M - Minutes
        # H - Hours
        # D - Days
        # midnight - roll over at midnight
        # W{0-6} - roll over on a certain day; 0 - Monday
        #
        # Case of the 'when' specifier is not important; lower or upper case
        # will work.
        if self.when == 'S':
            self.interval = 1  # one second
            self.suffix = '%Y-%m-%d_%H-%M-%S'
            self.extMatch = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$"
        elif self.when == 'M':
            self.interval = 60  # one minute
            self.suffix = '%Y-%m-%d_%H-%M'
            self.extMatch = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}$"
        elif self.when == 'H':
            self.interval = 60 * 60  # one hour
            self.suffix = '%Y-%m-%d_%H'
            self.extMatch = r"^\d{4}-\d{2}-\d{2}_\d{2}$"
        elif self.when == 'D' or self.when == 'MIDNIGHT':
            self.interval = 60 * 60 * 24  # one day
            self.suffix = '%Y-%m-%d'
            self.extMatch = r"^\d{4}-\d{2}-\d{2}$"
        elif self.when.startswith('W'):
            self.interval = 60 * 60 * 24 * 7  # one week
            if len(self.when) != 2:
                raise ValueError('You must specify a day for weekly rollover from 0 to 6 (0 is Monday): %s' % self.when)
            if self.when[1] < '0' or self.when[1] > '6':
                raise ValueError('Invalid day specified for weekly rollover: %s' % self.when)
            self.dayOfWeek = int(self.when[1])
            self.suffix = '%Y-%m-%d'
            self.extMatch = r"^\d{4}-\d{2}-\d{2}$"
        else:
            raise ValueError('Invalid rollover interval specified: %s' % self.when)

        self.extMatch = re.compile(self.extMatch)
        self.interval = self.interval * interval  # multiply by units requested
        if os.path.exists(filename):
            t = os.stat(filename)[ST_MTIME]
        else:
            t = int(time.time())
        self.rolloverAt = self.computeRollover(t)

        self.delay = delay
        self._rotateFailed = False
        self.backupCount = backupCount

        self._open_lockfile()
        # For debug mode, swap out the "_degrade()" method with a more a verbose one.
        if debug:
            self._degrade = self._degrade_debug

    def computeRollover(self, currentTime):
        """
        Work out the rollover time based on the specified time.
        """

        result = currentTime + self.interval
        # If we are rolling over at midnight or weekly, then the interval is already known.
        # What we need to figure out is WHEN the next interval is.  In other words,
        # if you are rolling over at midnight, then your base interval is 1 day,
        # but you want to start that one day clock at midnight, not now.  So, we
        # have to fudge the rolloverAt value in order to trigger the first rollover
        # at the right time.  After that, the regular interval will take care of
        # the rest.  Note that this code doesn't care about leap seconds. :)
        if self.when == 'MIDNIGHT' or self.when.startswith('W'):
            # This could be done with less code, but I wanted it to be clear
            if self.utc:
                t = time.gmtime(currentTime)
            else:
                t = time.localtime(currentTime)
            currentHour = t[3]
            currentMinute = t[4]
            currentSecond = t[5]
            # r is the number of seconds left between now and midnight
            r = _MIDNIGHT - ((currentHour * 60 + currentMinute) * 60 + currentSecond)
            result = currentTime + r
            # If we are rolling over on a certain day, add in the number of days until
            # the next rollover, but offset by 1 since we just calculated the time
            # until the next day starts.  There are three cases:
            # Case 1) The day to rollover is today; in this case, do nothing
            # Case 2) The day to rollover is further in the interval (i.e., today is
            #         day 2 (Wednesday) and rollover is on day 6 (Sunday).  Days to
            #         next rollover is simply 6 - 2 - 1, or 3.
            # Case 3) The day to rollover is behind us in the interval (i.e., today
            #         is day 5 (Saturday) and rollover is on day 3 (Thursday).
            #         Days to rollover is 6 - 5 + 3, or 4.  In this case, it's the
            #         number of days left in the current week (1) plus the number
            #         of days in the next week until the rollover day (3).
            # The calculations described in 2) and 3) above need to have a day added.
            # This is because the above time calculation takes us to midnight on this
            # day, i.e. the start of the next day.
            if self.when.startswith('W'):
                day = t[6]  # 0 is Monday
                if day != self.dayOfWeek:
                    if day < self.dayOfWeek:
                        daysToWait = self.dayOfWeek - day
                    else:
                        daysToWait = 6 - day + self.dayOfWeek + 1
                    newRolloverAt = result + daysToWait * (60 * 60 * 24)
                    if not self.utc:
                        dstNow = t[-1]
                        dstAtRollover = time.localtime(newRolloverAt)[-1]
                        if dstNow != dstAtRollover:
                            if not dstNow:  # DST kicks in before next rollover, so we need to deduct an hour
                                addend = -3600
                            else:
                                            # DST bows out before next rollover, so we need to add an hour
                                addend = 3600
                            newRolloverAt += addend
                    result = newRolloverAt
        return result

    def _open_lockfile(self):
        # Use 'file.lock' and not 'file.log.lock' (Only handles the normal "*.log" case.)
        if self.baseFilename.endswith('.log'):
            lock_file = self.baseFilename[:-4]
        else:
            lock_file = self.baseFilename
        lock_file += '.lock'
        self.stream_lock = open(lock_file, 'w')

    def _open(self, mode=None):
        """
        Open the current base file with the (original) mode and encoding.
        Return the resulting stream.

        Note:  Copied from stdlib.  Added option to override 'mode'
        """

        if mode is None:
            mode = self.mode
        if self.encoding is None:
            stream = open(self.baseFilename, mode)
        else:
            stream = codecs.open(self.baseFilename, mode, self.encoding)
        return stream

    def _close(self):
        """ Close file stream.  Unlike close(), we don't tear anything down, we
        expect the log to be re-opened after rotation."""

        if self.stream:
            try:
                if not self.stream.closed:
                    # Flushing probably isn't technically necessary, but it feels right
                    self.stream.flush()
                    self.stream.close()
            finally:
                self.stream = None

    def acquire(self):
        """ Acquire thread and file locks.  Re-opening log for 'degraded' mode.
        """

        # handle thread lock
        Handler.acquire(self)
        # Issue a file lock.  (This is inefficient for multiple active threads
        # within a single process. But if you're worried about high-performance,
        # you probably aren't using this log handler.)
        if self.stream_lock:
            # If stream_lock=None, then assume close() was called or something
            # else weird and ignore all file-level locks.
            if self.stream_lock.closed:
                # Daemonization can close all open file descriptors, see
                # https://bugzilla.redhat.com/show_bug.cgi?id=952929
                # Try opening the lock file again.  Should we warn() here?!?
                try:
                    self._open_lockfile()
                except Exception:
                    self.handleError(NullLogRecord())
                    # Don't try to open the stream lock again
                    self.stream_lock = None
                    return
            lock(self.stream_lock, LOCK_EX)

        # Stream will be opened as part by FileHandler.emit()

    def release(self):
        """ Release file and thread locks. If in 'degraded' mode, close the
        stream to reduce contention until the log files can be rotated. """

        try:
            if self._rotateFailed:
                self._close()
        except Exception:
            self.handleError(NullLogRecord())
        finally:
            try:
                if self.stream_lock and not self.stream_lock.closed:
                    unlock(self.stream_lock)
            except Exception:
                self.handleError(NullLogRecord())
            finally:
                # release thread lock
                Handler.release(self)

    def close(self):
        """
        Close log stream and stream_lock. """

        try:
            self._close()
            if not self.stream_lock.closed:
                self.stream_lock.close()
        finally:
            self.stream_lock = None
            Handler.close(self)

    def _degrade(self, degrade, msg, *args):
        """ Set degrade mode or not.  Ignore msg. """

        self._rotateFailed = degrade
        del msg  # avoid pychecker warnings
        del args

    def _degrade_debug(self, degrade, msg, *args):
        """ A more colorful version of _degade(). (This is enabled by passing
        "debug=True" at initialization).
        """

        if degrade:
            if not self._rotateFailed:
                sys.stderr.write('Degrade mode - ENTERING - (pid=%d)  %s\n' % (os.getpid(), msg % args))
                self._rotateFailed = True
        else:
            if self._rotateFailed:
                sys.stderr.write('Degrade mode - EXITING  - (pid=%d)   %s\n' % (os.getpid(), msg % args))
                self._rotateFailed = False

    def _next_rotation_filename(self, currentTime=None):
        # get the time that this sequence started at and make it a TimeTuple
        currentTime = currentTime or int(time.time())
        dstNow = time.localtime(currentTime)[-1]
        t = self.rolloverAt - self.interval
        if self.utc:
            timeTuple = time.gmtime(t)
        else:
            timeTuple = time.localtime(t)
            dstThen = timeTuple[-1]
            if dstNow != dstThen:
                if dstNow:
                    addend = 3600
                else:
                    addend = -3600
                timeTuple = time.localtime(t + addend)
        dfn = self.baseFilename + '.' + time.strftime(self.suffix, timeTuple)
        return dfn

    def _update_rollover_time(self, currentTime=None):
        currentTime = currentTime or int(time.time())
        dstNow = time.localtime(currentTime)[-1]

        newRolloverAt = self.computeRollover(currentTime)

        while newRolloverAt <= currentTime:
            newRolloverAt += self.interval

        # If DST changes and midnight or weekly rollover, adjust for this.
        if (self.when == 'MIDNIGHT' or self.when.startswith('W')) and not self.utc:
            dstAtRollover = time.localtime(newRolloverAt)[-1]
            if dstNow != dstAtRollover:
                if not dstNow:  # DST kicks in before next rollover, so we need to deduct an hour
                    addend = -3600
                else:
                                # DST bows out before next rollover, so we need to add an hour
                    addend = 3600
                newRolloverAt += addend

        self.rolloverAt = newRolloverAt

    def doRollover(self):
        """
        Do a rollover, as described in __init__().
        """

        self._close()
        if self.backupCount < 0:
            # Don't keep any backups, just overwrite the existing backup file
            # Locking doesn't much matter here; since we are overwriting it anyway
            self.stream = self._open('w')
            return

        try:
            # Determine if we can rename the log file or not. Windows refuses to
            # rename an open file, Unix is inode base so it doesn't care.

            # Attempt to rename logfile to tempname:  There is a slight race-condition here, but it seems unavoidable
            tmpname = None
            while not tmpname or os.path.exists(tmpname):
                tmpname = '%s.rotate.%08d' % (self.baseFilename, randint(0, 99999999))
            try:
                # Do a rename test to determine if we can successfully rename the log file
                os.rename(self.baseFilename, tmpname)
            except (IOError, OSError):
                exc_value = sys.exc_info()[1]
                self._degrade(True, 'rename failed.  File in use?  exception=%s', exc_value)
                return

            currentTime = int(time.time())
            dfn = self._next_rotation_filename(currentTime=currentTime)
            if os.path.exists(dfn):
                os.remove(dfn)

            # Issue 18940: A file may not have been created if delay is True.
            if os.path.exists(tmpname):
                # os.rename(self.baseFilename, dfn)
                os.rename(tmpname, dfn)
            if self.backupCount > 0:
                for s in self.getFilesToDelete():
                    os.remove(s)

            self._update_rollover_time(currentTime=currentTime)

            # print "%s -> %s" % (self.baseFilename, dfn)
            self._degrade(False, 'Rotation completed')
        finally:

            # Re-open the output stream, but if "delay" is enabled then wait
            # until the next emit() call. This could reduce rename contention in
            # some usage patterns.
            if not self.delay:
                self.stream = self._open()

    def shouldRollover(self, record):
        """
        Determine if rollover should occur.

        For those that are keeping track. This differs from the standard
        library's RotatingLogHandler class. Because there is no promise to keep
        the file size under maxBytes we ignore the length of the current record.
        """

        del record  # avoid pychecker warnings
        # Is stream is not yet open, skip rollover check. (Check will occur on
        # next message, after emit() calls _open())
        if self.stream is None:
            return False
        if self._shouldRollover():
            # If some other process already did the rollover (which is possible
            # on Unix) the file our stream may now be named "log.2014-09-30_16-42", thus
            # triggering another rollover. Avoid this

            replaced = True
            try:
                file_object_stat = os.fstat(self.stream.fileno())
                file_on_disk_stat = os.stat(self.baseFilename)
                replaced = not os.path.samestat(file_object_stat, file_on_disk_stat)
            except Exception as e:
                print('something went very wrong: {}'.format(e))

            if replaced:
                self._update_rollover_time()
                self._close()
                self.stream = self._open()

            return not replaced

        return False

    def _shouldRollover(self):
        t = int(time.time())
        if t >= self.rolloverAt:
            return True
        # print "No need to rollover: %d, %d" % (t, self.rolloverAt)
        self._degrade(False, 'Rotation done or not needed at this time')

        return False

    def getFilesToDelete(self):
        """
        Determine the files to delete when rolling over.

        More specific than the earlier method, which just used glob.glob().
        """

        dirName, baseName = os.path.split(self.baseFilename)
        fileNames = os.listdir(dirName)
        result = []
        prefix = baseName + '.'
        plen = len(prefix)
        for fileName in fileNames:
            if fileName[:plen] == prefix:
                suffix = fileName[plen:]
                if self.extMatch.match(suffix):
                    result.append(os.path.join(dirName, fileName))
        result.sort()
        if len(result) < self.backupCount:
            result = []
        else:
            result = result[:len(result) - self.backupCount]
        return result


# Publish this class to the "logging.handlers" module so that it can be use
# from a logging config file via logging.config.fileConfig().
import logging.handlers
logging.handlers.ConcurrentTimeRotatingFileHandler = ConcurrentTimeRotatingFileHandler
