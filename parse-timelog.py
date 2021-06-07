#!/usr/bin/env python3

import os
import sys
# We need the `regex` module instead of `re` for the branch reset feature
import regex
import argparse
import configparser
from pprint import pprint
from decimal import Decimal

SCRIPTDIR = os.path.normpath(os.path.dirname(__file__))
ENTRY_TIME_RE = regex.compile(r'^(?|(?:([0-9.]+)h)(?:(\d+)m)?|(?:([0-9.]+)h)?(?:(\d+)m))$')

config = configparser.ConfigParser()
config.read('config.ini')
HTML_ALIASES = config['html-aliases']
INTERNAL_PROJ_DESC = config['internal-project-desc']
PROJ_DESC = dict(INTERNAL_PROJ_DESC)
PROJ_DESC.update(config['project-desc'])
CURRENCY = config['rates']['currency']
HOURLY_RATE = Decimal(config['rates']['self'])
COMPANY_RATE = Decimal(config['rates']['company'])

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

class CommaSeparatedList(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        current = getattr(namespace, self.dest) or []
        # Convert comma-separated string to list
        additional = [v for v in value.split(',')]
        setattr(namespace, self.dest, current + additional)

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
parser.add_argument('--html', '-m', default=False, action='store_true',
                    help='Print HTML table rows instead of an ASCII table')
parser.add_argument('--company', '-c', default=False, action='store_true',
                    help='Print income for the company')
parser.add_argument('--ignore-projects', action=CommaSeparatedList, default=None,
                    help='Ignore this comma-separated list of projects')
options = parser.parse_args()
if not options.ignore_projects:
    options.ignore_projects = []

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

month_idx = 0
if len(timelog_monthly) > 1:
    month_idx = options.month_idx - 1
month, days = timelog_monthly[month_idx]
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
        if options.html and proj in HTML_ALIASES:
            proj = HTML_ALIASES[proj]
        if proj not in proj_hours:
            proj_hours[proj] = 0
        proj_hours[proj] += entry_time_to_minutes(entry_time)

def get_hhmmf(proj, hours, minutes):
    timef = '{:>4}{:<3}'
    if hours and minutes:
        return timef.format('{}h'.format(hours), '{}m'.format(minutes))
    elif hours:
        return timef.format('{}h'.format(hours), '')
    elif minutes:
        return timef.format('', '{}m'.format(minutes))
    raise AssertionError('No hours or minutes for {!r}'.format(proj))

def hm_to_h(hours, minutes):
    return round(hours + (minutes / 60), ndigits=2)

def get_decimalf(hours, minutes):
    timef = '{:>7}'
    hours = hm_to_h(hours, minutes)
    return timef.format(hours)

def get_timef(proj, hours, minutes):
    if options.decimal:
        return get_decimalf(hours, minutes)
    return get_hhmmf(proj, hours, minutes)

def split_minutes(minutes):
    hours = minutes // 60
    minutes = (minutes - (hours * 60))
    return hours, minutes

def get_cost(hours, minutes):
    hourly_rate = HOURLY_RATE if not options.company else COMPANY_RATE
    return hourly_rate * round(hours + minutes/60, ndigits=2)

def print_ascii_table(s):
    global month
    print('# {}'.format(month))
    print('{:<20} {:^7} {:>8}'.format('Project', 'Hours', 'Cost'))
    total_minutes = 0
    total_cost = 0
    for proj, minutes in s:
        if options.company and proj in INTERNAL_PROJ_DESC:
            continue
        total_minutes += minutes
        hours, minutes = split_minutes(minutes)
        cost = get_cost(hours, minutes)
        total_cost += cost
        print('{:<20} {} {:>8}'.format(proj, get_timef(proj, hours, minutes), cost))
    hours = total_minutes // 60
    minutes = (total_minutes - (hours * 60))
    print('{:<20} {} {:>8}'.format('Total:', get_timef('total', hours, minutes), total_cost))

def print_html_rows(s):
    global options
    indent = ' ' * 12
    tpl = \
'''{indent}{prefix}<tr>
{indent}  <td>{proj}</td>
{indent}  <td>{rate}</td>
{indent}  <td>{hours}</td>
{indent}  <td>{cost}</td>
{indent}</tr>{suffix}'''
    total_cost = 0
    ignored_minutes = 0
    d = {'rate': HOURLY_RATE, 'indent': indent}
    misc_proj = {'proj': [], 'minutes': Decimal(0)}
    for proj, minutes in s:
        # If less than 5h spent on something, put it in the misc projects list
        if proj not in INTERNAL_PROJ_DESC and minutes < 5 * 60:
            misc_proj['proj'].append(proj)
            misc_proj['minutes'] += minutes
            continue
        d['cost'] = get_cost(0, minutes)
        d['prefix'] = d['suffix'] = ''
        if proj in options.ignore_projects:
            d['prefix'] = '<!--'
            d['suffix'] = '-->'
            ignored_minutes += minutes
        else:
            total_cost += d['cost']
        d['proj'] = PROJ_DESC.get(proj, proj)
        d['hours'] = hm_to_h(0, minutes)
        print(tpl.format(**d))
    # Print one more row for the misc proj we accumulated above
    d['prefix'] = d['suffix'] = ''
    d['proj'] = INTERNAL_PROJ_DESC['-misc_proj'] + ' ' + ', '.join(misc_proj['proj'])
    d['hours'] = hm_to_h(0, misc_proj['minutes'])
    d['cost'] = get_cost(0, misc_proj['minutes'])
    total_cost += d['cost']
    print(tpl.format(**d))
    print('Total: {}{}'.format(CURRENCY, total_cost))
    if ignored_minutes > 0:
        print('Ignored hours: {}'.format(hm_to_h(0, ignored_minutes)))

# Print it all
s = [(k, proj_hours[k]) for k in sorted(proj_hours, key=proj_hours.get, reverse=True)]

if options.html:
    print_html_rows(s)
else:
    print_ascii_table(s)
