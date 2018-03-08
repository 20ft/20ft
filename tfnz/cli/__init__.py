# Copyright (c) 2018 David Preece, All rights reserved.
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
import argparse
import termios  # this *is* used and *can* be found
import tty
import select
import re
import logging
import os
from threading import Thread
from subprocess import check_call, CalledProcessError
from messidge import default_location
from tfnz.location import Location


def base_argparse(progname, location=True):
    parser = argparse.ArgumentParser(prog=progname)
    if location:
        connection_group = parser.add_argument_group('connection options')
        connection_group.add_argument('--location', help='use a non-default location', metavar='x.20ft.nz')
        connection_group.add_argument('--local', help='a non-dns ip for the location', metavar='x.local')
    return parser


def generic_cli(parser, implementations, *, quiet=True, location=True):
    args = parser.parse_args()
    dl = None
    loc = None

    if 'command' not in args:
        args.command = None

    if args.command is None and None not in implementations:
        parser.print_help()
        return

    # construct the location
    if location:
        try:
            dl = default_location(prefix="~/.20ft") if args.location is None else args.location
        except RuntimeError:
            print("There does not appear to be a 20ft account on this machine.", file=sys.stderr)
            sys.exit(1)

    # go
    try:
        if location:
            loc = Location(dl, location_ip=args.local, quiet=quiet)
        else:
            if not quiet:
                logging.basicConfig(level=logging.DEBUG)
        implementations[args.command](loc, args)
    except ValueError as e:
        print(str(e))
        exit(1)
    except KeyboardInterrupt:
        exit(1)
    finally:
        if loc is not None:
            loc.disconnect()
    exit(0)


# removes a flagged parameter from argv
# note: mutates argv
def remove_flagged(param, argv):
    flag_find = [a for a in enumerate(argv) if a[1] == param]
    if len(flag_find) == 1:
        del argv[flag_find[0][0]]  # flag
        del argv[flag_find[0][0]]  # and the value


def systemd(location, args, argv, preboot, cert):
    # note that this is *knee* *deep* in potential security holes but since it is connecting to
    # a non-multi-tenanted server under the user's control I'm not all that bothered about it.
    # you were warned

    # checks
    if '/' not in args.source:
        print("Use a tagged image (i.e. my/example) to create a service")
        return 1
    if '@' not in args.systemd:
        print("Please use a 'user@server' ssh connection string.")
    username = args.systemd.split('@')[0]

    # build the ssh command line
    if args.identity is None:
        ssh = ['ssh', args.systemd]
        sftp = 'sftp %s' % args.systemd
    else:
        ssh = ['ssh', '-i', args.identity, args.systemd]
        sftp = 'sftp -i %s %s' % (args.identity, args.systemd)

    # ensure file structure on the receiving machine
    service_name = args.source.replace('/', '-')
    path = '/home/%s/%s/' % (username, service_name)
    check_call(ssh + ['mkdir', '-p', path])

    # ensure the image is uploaded to the *location* (not the client-local server)
    location.ensure_image_uploaded(args.source)

    # copy any preboot files
    for source, _ in preboot:
        check_call('echo "put %s" | %s:%s' % (source, sftp, path), shell=True)

    # copy a certificate
    if cert is not None:
        check_call('echo "put %s" | %s:%s' % (cert[0], sftp, path), shell=True)
        check_call('echo "put %s" | %s:%s' % (cert[1], sftp, path), shell=True)
        if len(cert) == 3:
            check_call('echo "put %s" | %s:%s' % (cert[2], sftp, path), shell=True)

    # remove the procname, --systemd and --identity from argv
    del argv[0]
    remove_flagged('--systemd', argv)
    remove_flagged('--identity', argv)

    # render the unit file
    filename = service_name + '.service'
    with open(filename, 'w') as f:
        f.write('''
[Unit]
Description=20ft-%s

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/local/bin/tf %s
WorkingDirectory=%s
KillSignal=SIGINT
TimeoutStopSec=5
Restart=always
RestartSec=5
User=%s
Group=%s

[Install]
WantedBy=multi-user.target
    ''' % (args.source, ' '.join(argv), path, username, username))
    check_call('echo "put %s" | %s:%s\n' % (filename, sftp, path), shell=True)
    check_call(['rm', filename])

    # let systemd know
    try:
        check_call(ssh + ['sudo', 'ln', '-s', path + filename, '/etc/systemd/system/'])
    except CalledProcessError as e:
        print("WARNING: creating symlink into /etc/systemd/system failed - link may well be there already")
    check_call(ssh + ['sudo', 'systemctl', 'enable', service_name])
    check_call(ssh + ['sudo', 'systemctl', 'daemon-reload'])
    check_call(ssh + ['sudo', 'systemctl', 'start', service_name])


class Interactive:
    def __init__(self, location, container):
        self.stdin_attr = None
        self.location = location
        self.container = container
        self.exit_read, self.exit_write = os.pipe()
        self.thread = Thread(target=self.stdin_loop, name="Stdin loop")
        self.thread.start()

    def stdin_loop(self):
        # fails in debugger so we'll just ignore that
        print("Interactive session - escape is triple \'^]\'.", flush=True)
        try:
            tty.setraw(sys.stdin.fileno())
        except termios.error:
            pass

        # message loop
        while True:
            ready = select.select((sys.stdin, self.exit_read), (), ())
            if self.exit_read in ready[0]:
                return
            data = sys.stdin.read(1)
            self.location.call_on_main(self.container.stdin, (data.encode(),))

    @staticmethod
    def stdout_callback(obj, out):
        # strip nasty control code things
        parts = re.split(b'\x1b\[\d*n', out, maxsplit=1)
        sys.stdout.buffer.write(parts[0] + (parts[1] if len(parts) > 1 else b''))
        sys.stdout.flush()

    def stop(self, obj=None, code=None):
        # reset stdin if we can
        os.write(self.exit_write, b'\n')
