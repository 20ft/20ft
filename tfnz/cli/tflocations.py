#!/usr/local/bin/python3.5
# Copyright (c) 2017 David Preece, All rights reserved.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""A tiny utility to select from the location keys stored in ~/.20ft/"""

import os.path
from messidge import default_location
from tfnz.location import Location
from tfnz.cli import generic_cli, base_argparse


def main():
    parser = base_argparse('tflocations', location=False)
    subparsers = parser.add_subparsers(title='commands', dest='command')
    p_list = subparsers.add_parser('list', help='list locations with an account')
    p_token = subparsers.add_parser('select', help='select which location to use as default_location')
    p_token.add_argument('location', metavar='location.20ft.nz')

    generic_cli(parser, {'list': list_locations, 'select': select_location}, location=False)


def list_locations(location, args):
    # we have a match
    dl = default_location("~/.20ft")
    for loc in Location.all_locations():
        print("%s %s" % (loc, '<== default' if dl == loc else ''))


def select_location(location, args):
    # do a 'substring from left' match
    length = len(args.location)
    for loc in Location.all_locations():
        if loc[:length] == args.location:
            # we have a match
            with open(os.path.expanduser('~/.20ft/default_location'), 'w') as f:
                f.write(loc + "\n")
                return
    # failed
    print("Could not find a location starting with: " + args.location)
    exit(1)


if __name__ == "__main__":
    main()
