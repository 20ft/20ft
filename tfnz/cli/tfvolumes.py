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

import sys
from tfnz.cli import generic_cli, base_argparse


def main():
    parser = base_argparse('tfvolumes')
    subparsers = parser.add_subparsers(title='commands', dest='command')
    p_list = subparsers.add_parser('list', help='list available volumes')
    p_create = subparsers.add_parser('create', help='create a volume')
    p_create.add_argument('--sync', action='store_true', help='force synchronous updates')
    p_create.add_argument('tag', nargs='?', help='give the volume a tag')
    p_delete = subparsers.add_parser('destroy', help='destroy a volume')
    p_delete.add_argument('uuid')

    generic_cli(parser, {'list': list_vol, 'create': create_vol, 'destroy': destroy_vol})


def list_vol(location, args):
    for vol in location.all_volumes():
        print(vol.namespaced_display_name())


def create_vol(location, args):
    vol = location.create_volume(tag=args.tag, async=not args.sync)
    print(vol.namespaced_display_name())


def destroy_vol(location, args):
    try:
        vol = location.volumes.get(location.user_pk, key=args.uuid)
        location.destroy_volume(vol)
    except KeyError:
        print("Can't find volume: " + args.uuid)
        exit(1)


if __name__ == "__main__":
    main()
