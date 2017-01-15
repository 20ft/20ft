#!/usr/local/bin/python3.5
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

import argparse
import sys
import os
import json
import signal
from tfnz.location import Location, last_image

def main():
    parser = argparse.ArgumentParser(prog='tf')
    parser.add_argument('-v', action='count', help='Increase verbosity (up to 2)')
    parser.add_argument('--loc', help='Use a non-default location (fqdn)', metavar='xxx.20ft.nz')
    parser.add_argument('--local_ip', help='A non-dns ip for the broker', metavar='yyy.local')
    parser.add_argument('--bind', help='Bind to an address other than localhost', metavar='aa.bb.cc.dd')
    parser.add_argument('--offset', help='Offset to apply from the container exposed port', default=None)
    parser.add_argument('--json', help='Writes a file describing state (deleted on exit)', metavar="filename")
    parser.add_argument('--browser', action="store_true", help='Create web browser onto container port 80')
    parser.add_argument('--domain', help='Use a domain name other than \'localhost\' in HTTP', metavar="fake.domain")
    parser.add_argument('--path', help='HTTP path to use for the initial request', metavar="/what/ever")
    parser.add_argument('image', help='The Docker id of the launched image or \'.\'')
    parser.add_argument('env', help='Environment strings as ENV=value ...', nargs='*', default=[])
    args = parser.parse_args()

    # create a dictionary of the environment variables
    environment = {}
    for string in args.env:
        parts = string.split('=')
        if len(parts) != 2 or len(parts[1]) == 0:
            print("Pass environment variables in the form VARIABLE=value", file=sys.stderr)
            exit(3)
        environment[parts[0]] = parts[1]

    # see if we have another instance trying to write to json
    json_file = None
    if args.json is not None:
        try:
            json_file = open(args.json, 'x')
        except FileExistsError:
            print("Another tf process is holding file: " + args.json, file=sys.stderr)
            exit(4)

    # launch
    location = None
    node = None
    container = None
    try:
        if args.v is not None:
            location = Location(args.loc, args.local_ip, debug_log=(args.v == 2))
        else:
            location = Location(args.loc, args.local_ip)
    except BaseException as e:
        print("Failed while connecting to location: " + str(e), file=sys.stderr)
        exit(5)

    try:
        node = location.best_node()
    except BaseException as e:
        print("Failed while choosing node: " + str(e), file=sys.stderr)
        exit(6)

    try:
        if args.image == '.':
            args.image = last_image()
        container = node.spawn(args.image, env=environment)
    except BaseException as e:
        print("Failed while spawning container: " + str(e), file=sys.stderr)
        exit(7)

    # should we open some tunnels?
    ports = {}
    try:
        ports = container.docker_config['Config']['ExposedPorts']
    except KeyError:
        pass  # can't find any

    tunnels = []
    if not args.browser:
        for exposed in ports.keys():
            if len(exposed) < 4 or exposed[-4:] != '/tcp':
                continue
            try:
                lp = (int(exposed[:-4]) + int(args.offset)) if args.offset is not None else None
                tnl = container.attach_tunnel(int(exposed[:-4]),
                                              localport=lp,
                                              bind=args.bind)
            except ValueError:
                print("Offset needs to be an integer", file=sys.stderr)
                exit(10)

    # finally
    etc_hosts = None
    if args.browser:
        browser_domain = 'localhost' if args.domain is None else args.domain
        try:
            tnl = container.attach_browser(fqdn=browser_domain, path=args.path)
            tunnels.append(tnl)
        except NameError:  # doesn't resolve to localhost
            if os.geteuid() !=0:
                print("The address '%s' does not resolve to 127.0.0.1." % browser_domain, file=sys.stderr)
                print("Run this command again, prepending 'sudo' to have it fixed automatically.", file=sys.stderr)
                print("(running as any user able to edit /etc/hosts will also work)", file=sys.stderr)
                exit(8)
            else:
                with open('/etc/hosts', 'r') as f:
                    etc_hosts = f.read()
                with open('/etc/hosts', 'a') as f:
                    f.write('127.0.0.1 %s\n' % browser_domain)
                tnl = container.attach_browser(fqdn=browser_domain)
                tunnels.append(tnl)

    # write some json?
    if json_file is not None:
        root = dict()
        root['Container'] = {"uuid": str(container.uuid, 'ascii'), "image": container.image, "env": container.env}
        root['Tunnels'] = {tnl.port: tnl.localport for tnl in tunnels}
        root['pid'] = os.getpid()
        try:
            json_file.write(json.dumps(root))
            json_file.flush()
            print(root)
        except BaseException as e:
            print("Failed while writing json file: " + str(e), file=sys.stderr)
            exit(9)

    # sit here and twiddle our thumbs
    try:
        signal.pause()
    finally:
        # clean up
        if args.json:
            json_file.close()
            os.remove(args.json)
        if etc_hosts is not None:
            with open('/etc/hosts', 'w') as f:
                f.write(etc_hosts)

if __name__ == "__main__":
    main()

