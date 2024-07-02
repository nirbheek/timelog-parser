#!/usr/bin/env python3

import os
import sys
# We need the `regex` module instead of `re` for the branch reset feature
import regex
import argparse
import datetime
from pprint import pprint
from decimal import Decimal
from functools import cmp_to_key

SCRIPTDIR = os.path.normpath(os.path.dirname(__file__))
ENTRY_TIME_RE = regex.compile(r'^(?|(?:([0-9.]+)h)(?:(\d+)m)?|(?:([0-9.]+)h)?(?:(\d+)m))$')

def entry_time_to_minutes(t):
    global ENTRY_TIME_RE
    match = ENTRY_TIME_RE.match(t)
    if not match:
        raise AssertionError('Could not parse time entry {!r}'.format(t))
    h, m = match.groups()
    if not h and not m:
        raise AssertionError('Both hours and minutes are zero for time entry {!r}'.format(t))
    minutes = int(m) if m is not None else 0
    minutes += int(h) * 60 if h is not None else 0
    return minutes

def m_to_hm(m):
    h = m // 60
    m -= h * 60
    return f'{h}h{m}m'

def cmpf(a, b):
    if a > b:
        return 1
    if a < b:
        return -1
    return 0

def num_sort(a, b):
    a = a[0]
    b = b[0]
    if '-' not in a or '-' not in b:
        return cmpf(a, b)
    name1, num1 = a.split('-')
    name2, num2 = b.split('-')
    if name1 == name2:
        return int(num1) - int(num2)
    return cmpf(a, b)

parser = argparse.ArgumentParser(prog="parse-toa")
parser.add_argument('timelog_path', type=str, nargs='?', default=os.path.join(SCRIPTDIR, 'toa.txt'),
                    help='Path to TOA timelog file')
parser.add_argument('--decimal', '-d', default=False, action='store_true',
                    help='Show hours in decimal instead of XXhYYm format')
options = parser.parse_args()

timelog_f = open(options.timelog_path, 'r')
times = {}

for line in timelog_f:
    line = line.strip()
    if not line:
        continue
    try:
        task, hm = line.split(': ', maxsplit=1)
        minutes = entry_time_to_minutes(hm)
    except:
        print(line)
        raise
    if task in times:
        minutes += times[task]
    times[task] = minutes

for task, minutes in sorted(times.items(), key=cmp_to_key(num_sort)):
    if options.decimal:
        t = round(minutes / 60, ndigits=2)
    else:
        t = m_to_hm(minutes)
    print(f'{task:<7}: {t:^7}')

total_minutes = 0
for task, minutes in times.items():
    total_minutes += minutes
print(f'Total: {total_minutes/ 60:.2f}')
