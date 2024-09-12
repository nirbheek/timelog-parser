#!/usr/bin/env python3

import os
import sys
# We need the `regex` module instead of `re` for the branch reset feature
import regex
import argparse
import calendar
import datetime
import configparser
from pprint import pprint
from decimal import Decimal

SCRIPTDIR = os.path.normpath(os.path.dirname(__file__))
ENTRY_TIME_RE = regex.compile(r'^(?|(?:([0-9.]+)h)(?:(\d+)m)?|(?:([0-9.]+)h)?(?:(\d+)m))$')
ENTRY_COLLAPSE_THRESHOLD = 4 * 60

config = configparser.ConfigParser()
config.read('config.ini')
try:
    PROJECT_ALIASES = config['project-aliases']
except KeyError:
    PROJECT_ALIASES = config['html-aliases']
INTERNAL_PROJ_DESC = config['internal-project-desc']
try:
    INVOICE = config['invoice']
except KeyError:
    INVOICE = None

PROJ_DESC = dict(INTERNAL_PROJ_DESC)
PROJ_DESC.update(config['project-desc'])
CURRENCY = config['rates']['currency']
HOURLY_RATE = Decimal(config['rates']['self'])
COMPANY_RATE = Decimal(config['rates']['company'])
try:
    CURRENCY_NAME = config['rates']['currency-name']
except KeyError:
    CURRENCY_NAME = ''

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
parser.add_argument('--csv', '-s', default=False, action='store_true',
                    help='Print CSV instead of an ASCII table')
parser.add_argument('--company', '-c', default=False, action='store_true',
                    help='Print income for the company')
parser.add_argument('--ignore-projects', action=CommaSeparatedList, default=None,
                    help='Ignore this comma-separated list of projects')
parser.add_argument('--today', default=False, action='store_true',
                    help='Show time spent today')
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
month_desc = None
# Split timelog into monthwise entries
for line in timelog_f:
    # First, skip starting of file which is in a different format till we get
    # a month entry, after which the format is more consistent
    if not month_desc and not line.startswith('== '):
        continue
    if line.startswith('# '):
        continue
    if line.startswith('== '):
        month_desc = line[3:-1]
        month_entries = []
        timelog_monthly.append((month_desc, month_entries))
        continue
    if line[:-1]:
        month_entries.append(line[:-1])

month_idx = 0
if options.today:
    month_idx = -1
elif len(timelog_monthly) > 1:
    month_idx = options.month_idx - 1
month_desc, lines = timelog_monthly[month_idx]
if options.today:
    lines = lines[-1:]
# format:
# {
#   'project1': hours,
#   'project2': hours,
#   ...,
# }
proj_hours = {}
# format:
# {
#   'bonus1': amount,
#   'bonus2': amount,
#   ...,
# }
bonus_amounts = {}
# format:
# {
#   'expense1': cost,
#   'expense2': cost,
#   ...,
# }
expenses = {}
# Aggregate per-category hours from this month's entries
for line in lines:
    desc, items = line.split(': ', maxsplit=1)
    if desc.startswith('expense'):
        expense, cost = items.rsplit(': ', maxsplit=1)
        # Skip any comments
        if '#' in cost:
            cost = cost.split('#')[0]
        if ', ' in cost:
            unit_amount, quantity = cost.split(', ')
            expenses[expense] = [Decimal(unit_amount), int(quantity)]
        else:
            amount = Decimal(cost)
            expenses[expense] = [amount, 1]
    elif desc.startswith('bonus'):
        bonus, amount = items.rsplit(': ', maxsplit=1)
        bonus_amounts[bonus] = [Decimal(amount), 1]
    else:
        entries = items.split(', ')
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
            if (options.html or options.csv) and proj in PROJECT_ALIASES:
                proj = PROJECT_ALIASES[proj]
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

def get_hourly_rate():
    return HOURLY_RATE if not options.company else COMPANY_RATE

def get_cost(hours, minutes):
    hourly_rate = get_hourly_rate()
    return hourly_rate * hm_to_h(hours, minutes)

def is_travel_expense(desc):
    kws = ('travel', 'cab', 'flight', 'taxi', 'insurance', 'conf', 'hackfest',
           'ticket', 'hotel', 'food', 'visa', 'vfs')
    desc = desc.lower()
    for kw in kws:
        if kw in desc:
            return True
    return False

def print_ascii_table(s):
    global month_desc
    print('# {}'.format(month_desc))
    print('{:<20} {:^7} {:>8}'.format('Project', 'Hours', 'Cost'))
    total_minutes = 0
    total_cost = 0
    for proj, minutes in s:
        if options.company and proj in INTERNAL_PROJ_DESC:
            continue
        if not options.today and ('NOT&M' in proj or 'NOTM' in proj):
            continue
        total_minutes += minutes
        hours, minutes = split_minutes(minutes)
        cost = get_cost(hours, minutes)
        total_cost += cost
        print('{:<20} {} {:>8}'.format(proj, get_timef(proj, hours, minutes), cost))
    hours, minutes = split_minutes(total_minutes)
    # The total is approximate here because the way we add up "misc client
    # projects" is different here compared to csv and html row printing. Here
    # we calculate the cost of each item immediately and add it to the total
    # cost, whereas there we aggregate the minutes spent on each item and
    # convert it to cost later.
    print('{:<20} {} {:>8}'.format('Total (approx):', get_timef('total', hours, minutes), total_cost))

def print_html_rows(s, b, e):
    global options
    indent = ' ' * 12
    tpl = \
'''{indent}{prefix}<tr>
{indent}  <td>{desc}</td>
{indent}  <td>{unit_amount}</td>
{indent}  <td>{quantity}</td>
{indent}  <td>{amount:.2f}</td>
{indent}</tr>{suffix}'''
    total_amount = 0
    ignored_minutes = 0
    d = {'unit_amount': HOURLY_RATE, 'indent': indent}
    misc_proj = {'desc': [], 'minutes': Decimal(0)}
    for proj, minutes in s:
        # If less than 4h spent on something, put it in the misc projects list
        if proj not in INTERNAL_PROJ_DESC and minutes < ENTRY_COLLAPSE_THRESHOLD:
            proj_name = PROJ_DESC.get(proj, proj).split(':')[0]
            misc_proj['desc'].append(proj_name)
            misc_proj['minutes'] += minutes
            continue
        d['amount'] = get_cost(0, minutes)
        d['prefix'] = d['suffix'] = ''
        if proj in options.ignore_projects:
            d['prefix'] = '<!--'
            d['suffix'] = '-->'
            ignored_minutes += minutes
        else:
            total_amount += d['amount']
        d['desc'] = PROJ_DESC.get(proj, proj)
        d['quantity'] = hm_to_h(0, minutes)
        print(tpl.format(**d))
    # Print one more row for the misc proj we accumulated above
    if misc_proj['desc']:
        d['prefix'] = d['suffix'] = ''
        mp = misc_proj['desc']
        if len(mp) > 3:
            mp = mp[:3] + ['etc']
        d['desc'] = INTERNAL_PROJ_DESC['-misc_proj'] + ' ' + ', '.join(mp)
        d['quantity'] = hm_to_h(0, misc_proj['minutes'])
        d['amount'] = get_cost(0, misc_proj['minutes'])
        total_amount += d['amount']
        print(tpl.format(**d))
    # Print bonuses (if any)
    for desc, (unit_amount, quantity) in b.items():
        d['desc'] = desc
        d['unit_amount'] = unit_amount
        d['quantity'] = quantity
        d['amount'] = unit_amount * quantity
        total_amount += d['amount']
        print(tpl.format(**d))
    print()
    # Print expenses
    for desc, (unit_amount, quantity) in e.items():
        d['desc'] = desc
        d['unit_amount'] = unit_amount
        d['quantity'] = quantity
        d['amount'] = unit_amount * quantity
        total_amount += d['amount']
        print(tpl.format(**d))
    print('Total: {}{}'.format(CURRENCY, total_amount))
    if ignored_minutes > 0:
        print('Ignored hours: {}'.format(hm_to_h(0, ignored_minutes)))

def get_row(desc, unit_amount, quantity, account_code, tax_type, invoice_date=None, total_amount=None):
    row = [INVOICE['name']]
    optional_config_fields = [
        'email', 'address1', 'address2', 'address3', 'address4',
        'address-city', 'address-region', 'address-postalcode',
        'address-country',
    ]
    for field in optional_config_fields:
        row.append(INVOICE.get(field, ''))
    # Invoice number
    row.append(f'Invoice 001-{invoice_date.year}-{invoice_date.month:02d}')
    # Invoice date
    row.append(invoice_date.strftime('%d/%m/%Y'))
    # Due date is + 60 days
    due_date = invoice_date + datetime.timedelta(days=60)
    row.append(due_date.strftime('%d/%m/%Y'))
    # Total amount
    row.append(str(total_amount))
    # InventoryItemCode
    row.append('')
    row += [desc, quantity, unit_amount, account_code, tax_type]
    # TaxAmount,TrackingName1,TrackingOption1,TrackingName2,TrackingOption2,Currency
    row += ['', '', '', '', '', CURRENCY_NAME]
    return row

def write_csv_rows(s, b, e):
    import csv
    global options
    rows = []
    total_amount = Decimal(0)
    rate = get_hourly_rate()
    misc_proj = {'proj': [], 'minutes': Decimal(0)}
    for proj, minutes in s:
        # If less than 4h spent on something, put it in the misc projects list
        if proj not in INTERNAL_PROJ_DESC and minutes < ENTRY_COLLAPSE_THRESHOLD:
            proj_name = PROJ_DESC.get(proj, proj).split(':')[0]
            misc_proj['proj'].append(proj_name)
            misc_proj['minutes'] += minutes
            continue
        quantity = hm_to_h(0, minutes)
        desc = 'Software development services: ' + PROJ_DESC.get(proj, proj)
        rows.append([desc, rate, quantity, '330', 'Reverse Charge Expenses (20%)'])
        total_amount += rate * quantity
    if misc_proj['proj']:
        mp = misc_proj['proj']
        if len(mp) > 3:
            mp = mp[:3] + ['etc']
        desc = INTERNAL_PROJ_DESC['-misc_proj'] + ' ' + ', '.join(mp)
        desc = 'Software development services: ' + desc
        quantity = hm_to_h(0, misc_proj['minutes'])
        rows.append([desc, rate, quantity, '330', 'Reverse Charge Expenses (20%)'])
        total_amount += rate * quantity
    # Print bonuses
    for desc, (unit_amount, quantity) in b.items():
        desc = 'Software development services: ' + desc
        acc_code = '330'
        acc_desc = 'Reverse Charge Expenses (20%)'
        rows.append([desc, unit_amount, quantity, acc_code, acc_desc])
        total_amount += unit_amount * quantity
    # Print expenses
    for desc, (unit_amount, quantity) in e.items():
        accounting_code = None
        if 'Bank' in desc:
            acc_code = '404'
            acc_desc = 'No VAT'
        elif is_travel_expense(desc):
            acc_code = '494'
            acc_desc = 'No VAT'
        else:
            acc_code = '464' # Default to electronics
            acc_desc = 'No VAT'
        desc = desc.replace('¹', '')
        rows.append([desc, unit_amount, quantity, acc_code, acc_desc])
        total_amount += unit_amount * quantity

    # Get the invoice date
    month, year = month_desc.split(' ', maxsplit=1)
    year = int(year)
    if len(month) == 3:
        month = datetime.datetime.strptime(month, '%b').month
    else:
        month = datetime.datetime.strptime(month, '%B').month
    day = calendar.monthrange(year, month)[1]
    invoice_date = datetime.date(year, month, day)

    fname = '{}_{}.csv'.format(INVOICE['name'].split()[0], invoice_date.strftime('%Y-%m-%d'))
    if os.path.exists(fname):
        print(f'{fname} exists, skipping')
        return
    with open(fname, 'w') as f:
        w = csv.writer(f)
        w.writerow([
            'ContactName', 'EmailAddress', 'POAddressLine1', 'POAddressLine2',
            'POAddressLine3', 'POAddressLine4', 'POCity', 'PORegion',
            'POPostalCode', 'POCountry', 'InvoiceNumber', 'InvoiceDate', 'DueDate',
            'Total', 'InventoryItemCode', 'Description', 'Quantity', 'UnitAmount',
            'AccountCode', 'TaxType', 'TaxAmount', 'TrackingName1',
            'TrackingOption1', 'TrackingName2', 'TrackingOption2', 'Currency'
        ])
        for each in rows:
            w.writerow(get_row(*each, invoice_date=invoice_date, total_amount=total_amount))
    print(f'Wrote to {fname}', file=sys.stderr)
    print(f'Total amount: {total_amount}', file=sys.stderr)

# Print it all
s = [(k, proj_hours[k]) for k in sorted(proj_hours, key=proj_hours.get, reverse=True)]

if options.html:
    print_html_rows(s, bonus_amounts, expenses)
elif options.csv:
    write_csv_rows(s, bonus_amounts, expenses)
else:
    print_ascii_table(s)
