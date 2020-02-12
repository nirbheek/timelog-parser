#!/usr/bin/env python3

import os
import sys
# We need the `regex` module instead of `re` for the branch reset feature
import regex
import argparse
from pprint import pprint
from decimal import Decimal

SCRIPTDIR = os.path.normpath(os.path.dirname(__file__))
ENTRY_TIME_RE = regex.compile(r'^(?|(?:([0-9.]+)h)(?:(\d+)m)?|(?:([0-9.]+)h)?(?:(\d+)m))$')
HOURLY_RATE = 0

def entry_time_to_minutes(t):
    global ENTRY_TIME_RE
    match = ENTRY_TIME_RE.match(t)
    if not match:
        raise AssertionError('Could not parse time entry {!r}'.format(t))
    h, m = match.groups()
    if not h and not m:
        raise AssertionError('Both hours and minutes are zero for time entry {!r}'.format(t))
    minutes = Decimal(m) if m is not None else 0
    minutes += Decimal(h) * 60 if h is not None else 0
    return minutes

# Parse arguments
parser = argparse.ArgumentParser(prog="parse-timelog")
parser.add_argument('timelog_path', type=str, nargs='?', default=os.path.join(SCRIPTDIR, 'time-spent.txt'),
                    help='Path to timelog file')
parser.add_argument('month_idx', type=int, nargs='?', default=-1,
                    help='Month index to parse')
parser.add_argument('--project-detail', '-p', default=False, action='store_true',
                    help='Summarize by project detail in the summary, not just by project')
parser.add_argument('--decimal', '-d', default=False, action='store_true',
                    help='Show hours in decimal instead of XXhYYm format')
options = parser.parse_args()

# Start parsing timelog
timelog_f = open(options.timelog_path, 'r')

# format:
# [
#   (month1, [line1, line2, line3, ..]),
#   (month2, [line1, ...]),
#   ...,
# ]
timelog_monthly = []
month = None
# Split timelog into monthwise entries
for line in timelog_f:
    # First, skip starting of file which is in a different format till we get
    # a month entry, after which the format is more consistent
    if not month and not line.startswith('== '):
        continue
    if line.startswith('== '):
        month = line[3:-1]
        month_entries = []
        timelog_monthly.append((month, month_entries))
        continue
    if line[:-1]:
        month_entries.append(line[:-1])

month, days = timelog_monthly[options.month_idx - 1]
# format:
# {
#   'project1': hours,
#   'project2': hours,
#   ...,
# }
proj_hours = {}
# Aggregate per-category hours from this month's entries
for day in days:
    entries = day.split(': ', maxsplit=1)[1].split(', ')
    for entry in entries:
        try:
            ret = entry.split(' of ', maxsplit=1)
            if len(ret) != 2:
                print('Ignoring invalid/unknown entry {!r}'.format(entry))
                continue
            entry_time, proj = ret
        except ValueError:
            print(entry)
            raise
        if ' at ' in proj:
            proj = proj.split(' at ', maxsplit=1)[0]
        if not options.project_detail:
            proj = proj.split(sep='-', maxsplit=1)[0]
        if proj not in proj_hours:
            proj_hours[proj] = 0
        proj_hours[proj] += entry_time_to_minutes(entry_time)

def get_hhmmf(proj, hours, minutes):
    timef = '{:>3}{:<3}'
    if hours and minutes:
        return timef.format('{}h'.format(hours), '{}m'.format(minutes))
    elif hours:
        return timef.format('{}h'.format(hours), '')
    elif minutes:
        return timef.format('', '{}m'.format(minutes))
    raise AssertionError('No hours or minutes for {!r}'.format(proj))

def get_decimalf(proj, hours, minutes):
    timef = '{:>6.2f}'
    hours = hours + (minutes / 60)
    return timef.format(hours)

def get_timef(proj, hours, minutes):
    if options.decimal:
        return get_decimalf(proj, hours, minutes)
    return get_hhmmf(proj, hours, minutes)

def split_minutes(minutes):
    hours = minutes // 60
    minutes = (minutes - (hours * 60))
    return hours, minutes

def get_cost(hours, minutes):
    return HOURLY_RATE * round(hours + minutes/60, ndigits=2)

def print_ascii_table(s):
    global month
    print('# {}'.format(month))
    print('{:<20} {:^6} {:>8}'.format('Project', 'Hours', 'Cost'))
    total_minutes = 0
    total_cost = 0
    for proj, minutes in s:
        total_minutes += minutes
        hours, minutes = split_minutes(minutes)
        cost = get_cost(hours, minutes)
        total_cost += cost
        print('{:<20} {} {:>8}'.format(proj, get_timef(proj, hours, minutes), cost))
    hours = total_minutes // 60
    minutes = (total_minutes - (hours * 60))
    print('{:<20} {} {:>8}'.format('Total:', get_timef('total', hours, minutes), total_cost))

# Print it all
s = [(k, proj_hours[k]) for k in sorted(proj_hours, key=proj_hours.get, reverse=True)]
print_ascii_table(s)
