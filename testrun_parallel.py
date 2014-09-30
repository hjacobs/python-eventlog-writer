#!/usr/bin/env python
# -*- coding: utf-8 -*-

############## Quick multiprocess stress test to see if logging is done properly ##############

import time
from multiprocessing import Process
import math
import random
import os
import eventlog

# you change the rotation to size based
eventlog.filesize_rotation = False
eventlog.rotation_maxBytes = 5242880
eventlog.rotation_backupCount = 9
eventlog.rotation_when = 'M'

NUM_PROCESSES = 64
DELAY = [0.01, 0.03]
EXPLORE_PRIMES = [2, 900000]

# register the events we will use
my_event_id = 0x34888


# eventlog.register(my_event_id, 'EVENTO_INUTIL', *['workerPid', 'integer', 'isPrime'])

def log_event(pid, n, is_prime):

    print 'log_event pid={}, n={}, is_prime={}'.format(pid, n, is_prime)

    parms = {'workerPid': pid, 'integer': n, 'isPrime': is_prime}
    eventlog.log(my_event_id, **parms)


def is_prime(n):

    my_pid = os.getpid()

    time.sleep(random.uniform(*DELAY))
    # time.sleep(1)

    if n % 2 == 0:
        log_event(my_pid, n, False)
        return False

    sqrt_n = int(math.floor(math.sqrt(n)))
    for i in range(3, sqrt_n + 1, 2):
        if n % i == 0:
            log_event(my_pid, n, False)
            return False

    log_event(my_pid, n, True)
    return True


def job_primes(process_index, total_processes, Nstart, Nend):

    # register the events we will use, MUST be done inside the child process (after the fork) !!!
    eventlog.register(my_event_id, 'EVENTO_INUTIL', *['workerPid', 'integer', 'isPrime'])

    n = Nstart + process_index
    while n < Nend:
        is_prime(n)
        n += total_processes


def testrun_parallel():

    # spawn some processes
    procs = []
    for i in range(NUM_PROCESSES):
        p = Process(target=job_primes, args=(i, NUM_PROCESSES, EXPLORE_PRIMES[0], EXPLORE_PRIMES[1]))
        procs.append(p)
        p.start()

    # wait for child processes to finish
    for p in procs:
        p.join()


if __name__ == '__main__':

    os.system('rm eventlog.log* eventlog.layout* eventlog.lock')

    testrun_parallel()

    status1 = os.system('test `cat eventlog.log* | wc -l` -eq {}'.format(EXPLORE_PRIMES[1] - EXPLORE_PRIMES[0]))
    status2 = os.system('test -z "`cat eventlog.log* | awk \'{print $5}\' | uniq -d`"')

    if status1 == 0 and status2 == 0:
        print 'Number of log entries is correct'
    else:
        print 'Number of log entries is wrong!!!!'
