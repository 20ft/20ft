"""
Copyright (c) 2017 David Preece, All rights reserved.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""
import sys
import argparse
import termios
import tty
import select
import re
from messidge import default_location
from tfnz.location import Location


def base_argparse(progname):
    parser = argparse.ArgumentParser(prog=progname)
    connection_group = parser.add_argument_group('connection options')
    connection_group.add_argument('--location', help='use a non-default location', metavar='x.20ft.nz')
    connection_group.add_argument('--local', help='a non-dns ip for the location', metavar='x.local')
    return parser


def generic_cli(parser, implementations, *, quiet=True):
    args = parser.parse_args()

    if 'command' not in args:
        args.command = None

    if args.command is None and None not in implementations:
        parser.print_help()
        return

    # construct the location
    try:
        dl = default_location(prefix="~/.20ft") if args.location is None else args.location
    except RuntimeError:
        print("There does not appear to be a 20ft account on this machine.", file=sys.stderr)
        sys.exit(1)

    # go
    location = None
    try:
        location = Location(dl, location_ip=args.local, quiet=quiet)
        implementations[args.command](location, args)
    except ValueError as e:
        print(str(e))
        exit(1)
    except KeyboardInterrupt:
        exit(1)
    finally:
        if location is not None:
            location.disconnect()
    exit(0)


class Interactive:
    def __init__(self, loc):
        self.shown_escape_info = False
        self.term_attr = termios.tcgetattr(sys.stdout.fileno())
        self.location = loc
        self.running = True

    def stdin_loop(self, container):
        # do we need to let the user know?
        if not self.shown_escape_info:
            print("Interactive session - escape is triple \'^]\'.")
            self.shown_escape_info = True

        tty.setraw(sys.stdin.fileno())
        while self.running:
            ready = select.select((sys.stdin,), (), (), 0.5)
            if len(ready[0]) != 0:
                data = sys.stdin.read(1)
                container.stdin(data.encode())

    def stdout_callback(self, ctr, out):
        # strip nasty control code things
        parts = re.split(b'\x1b\[\d*n', out, maxsplit=1)
        sys.stdout.buffer.write(parts[0] + (parts[1] if len(parts) > 1 else b''))
        sys.stdout.flush()

    @staticmethod
    def stdout_flush(out):
        sys.stdout.buffer.write(out)
        sys.stdout.flush()

    def termination_callback(self, ctr):
        self.running = False
        termios.tcsetattr(sys.stdout.fileno(), termios.TCSANOW, self.term_attr)
        self.location.disconnect()
