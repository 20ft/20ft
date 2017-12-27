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


# the method to implement is tf_main(location, node, environment, portmap, pass_args)

import argparse
import sys
import signal
import re
import os
import os.path
from sys import exit, argv, stderr
from messidge import default_location, create_account
from tfnz.location import Location
from tfnz.volume import Volume
from tfnz.docker import Docker
from tfnz.endpoint import Cluster
from tfnz.cli import base_argparse, systemd, Interactive


def main_impl():
    # see if we have an account
    try:
        default_location(prefix="~/.20ft")
    except RuntimeError:
        # there is no default location
        if len(argv) != 3:
            print("""
There is no a 20ft account on this machine, you need to request 
access from your administrator.

If you already have an account on another machine you can merely 
copy the directory ~/.20ft (and it's contents) to this machine.""", file=stderr)
            return None

        # trying to create a new account using token passed by the server
        create_account(argv[1], argv[2], prefix="~/.20ft")
        print("Created OK for: %s\n" % argv[1])
        return None

    # right, get on with it
    parser = base_argparse('tf')
    launch_group = parser.add_argument_group('launch options')
    launch_group.add_argument('-v', help='verbose logging', action='store_true')
    launch_group.add_argument('-q', help='no logging', action='store_true')
    launch_group.add_argument('-i', help='interactive', action='store_true')
    launch_group.add_argument('-e', help='set an environment variable', action='append', metavar='VAR=value')
    launch_group.add_argument('-f', help='write a pre-boot file', action='append', metavar='src:dest')
    launch_group.add_argument('-m', help='mount a volume', action='append', metavar='uuid:mountpoint')
    launch_group.add_argument('-p', help='add a local->remote tcp proxy', action='append', metavar='8080:80')
    launch_group.add_argument('-r', help="add a remote->local tcp proxy", action='append', metavar='55555')
    launch_group.add_argument('-c', help='use this command (in container) to start', metavar='script.sh')
    launch_group.add_argument('-w', help='publish on web endpoint',
                              metavar='subdomain.my.com[:www.my.com[:certname]]')
    interactive_group = parser.add_argument_group('local/interactive options')
    interactive_group.add_argument('--ssh', help='create an ssh/sftp wrapped shell on given port', metavar='2222')
    interactive_group.add_argument('-s', help='short form for "--ssh 2222"', action='store_true')
    interactive_group.add_argument('-z', help='launch the container asleep (instead of cmd)', action='store_true')
    server_group = parser.add_argument_group('server options')
    server_group.add_argument('--systemd', help='create a systemd service', metavar='user@tinyserver.my.com')
    server_group.add_argument('--identity', help='specify an identity file')

    parser.add_argument('source', help="if '.', runs the most recently added docker image; "
                                       "else this is the tag or hex id of an image to run.")
    parser.add_argument('args', help='arguments to pass to a script or subprocess (you may need "--", see man page)',
                        nargs=argparse.REMAINDER)
    args = parser.parse_args()

    # collect any pre-boot files
    preboot = []
    if args.f is not None:
        for e in args.f:
            match = re.match('^[\w:]*[\w.\-\\/]+:[\w.\-\\/]+$', e)
            if not match:
                print("Pre-boot copies need to be in source:destination pairs", file=sys.stderr)
                print("....error in '%s'" % e, file=sys.stderr)
                return None
            files = e.split(':')
            # are we copying into a directory? append the original filename
            if files[1][-1:] == '/':
                files[1] += files[0]
            # try to read the file in
            try:
                with open(files[0], 'rb') as f:
                    preboot.append((files[1], f.read()))
            except FileNotFoundError:
                print("Could not find the source pre-boot file: " + files[0], file=sys.stderr)
                return None

    # if publishing to an endpoint, we might need ssl certs
    endpoint = None
    rewrite = None
    cert = None
    fqdns = None
    if args.w is not None:
        # split into endpoint:rewrite:certname (rewrite and certname are optional)
        fqdns = args.w.split(':')
        if len(fqdns) == 0 or len(fqdns[0]) == 0:
            print("Cannot publish to an endpoint without an address", file=sys.stderr)
            return None
        endpoint = fqdns[0]

        if len(fqdns) > 1 and len(fqdns[1]) > 0:
            rewrite = fqdns[1]

        if len(fqdns) > 2 and len(fqdns[2]) > 0:
            cert = (fqdns[2] + '.crt', fqdns[2] + '.key')
            if not os.path.exists(cert[0]):
                print("Cannot find certificate for ssl: " + cert[0], file=sys.stderr)
                return None
            if not os.path.exists(cert[1]):
                print("Cannot find key for ssl: " + cert[1], file=sys.stderr)
                return None

    # connect
    location = None
    try:
        location = Location(args.location, location_ip=args.local, quiet=args.q, debug_log=args.v)
    except BaseException as e:
        print("Failed while connecting to location: " + str(e), file=sys.stderr)
        return location

    # are we making a systemd service?
    if args.systemd is not None:
        systemd(location, args, argv, preboot, cert)
        return location

    # are we going to be using the most recent build?
    if args.source == '.':
        args.source = Docker.last_image()

    # maybe remove --
    if len(args.args) > 0:
        if args.args[0] == '--':
            del args.args[0]

    # create env-vars
    e_vars = set()
    environment = []
    if args.e is not None:
        for e in args.e:
            match = re.match('[0-9A-Za-z:_]+=', e)
            if not match:
                print("Environment variables need to be passed as 'name=value' pairs", file=sys.stderr)
                print("....error in '%s'" % e, file=sys.stderr)
                return location
            variable = match.group(0)[:-1]
            if variable in e_vars:
                print("Can only pass one value per environment variable.", file=sys.stderr)
                print("....error in '%s'" % e, file=sys.stderr)
                return location
            value = e[len(variable)+1:]
            e_vars.add(variable)
            environment.append((variable, value))

    # create portmaps
    l_ports = set()
    portmap = []
    if args.p is not None:
        for e in args.p:
            match = re.match('\d+:\d+$', e)
            if not match:
                print("Portmaps need to be passed as number:number pairs", file=sys.stderr)
                print("....error in '%s'" % e, file=sys.stderr)
                return location
            local, remote = e.split(':')
            if local in l_ports:
                print("Cannot bind a local port twice.", file=sys.stderr)
                print("....error in '%s'" % e, file=sys.stderr)
                return location
            l_ports.add(local)
            portmap.append((local, remote))

    # create volume mounts ensuring they don't overlap
    volumes = []
    mount_points = set()
    if args.m is not None:
        for m in args.m:
            if ':' not in m:
                print("Volumes need to be passed as uuid:mountpoint pairs", file=sys.stderr)
                print("....error in '%s'" % m, file=sys.stderr)
                return location
            find = m.rfind(':')
            key = m[:find]
            mount = m[find+1:]
            intersection = Volume.trees_intersect(mount_points, mount)
            if intersection is not None:
                print("Error in volumes: %s is a subtree of %s" % (intersection[0], intersection[1]), file=sys.stderr)
                return location
            try:
                volumes.append((location.volumes.get(location.user_pk, key), mount))
            except KeyError:
                print("Could not find volume: " + key)
                return location
            mount_points.add(mount)

    # try to launch the container
    interactive = Interactive(location) if args.i else None
    try:
        node = location.node()
        container = node.spawn_container(args.source,
                                         env=environment,
                                         pre_boot_files=preboot,
                                         volumes=volumes,
                                         stdout_callback=(interactive.stdout_callback if args.i
                                                          else lambda _, out: Interactive.stdout_flush(out)),
                                         termination_callback=(interactive.termination_callback if args.i
                                                               else location.disconnect),
                                         command=args.c,
                                         sleep=args.z)
        container.wait_until_ready()  # a transport for exceptions
    except BaseException as e:
        print("Failed while spawning container: " + str(e), file=sys.stderr)
        return location

    # create the tunnels
    for m in portmap:
        container.attach_tunnel(m[1], m[0])

    # backchannels
    if args.r is not None:
        for r in args.r:
            container.create_backchannel(int(r))

    # launch an ssh server? user/pass are anything/anything - you can only connect from localhost anyway
    if args.ssh or args.s:
        container.create_ssh_server(2222 if args.s else int(args.ssh))

    # publish to an endpoint?
    if args.w is not None:
        container.wait_until_ready()
        clstr = Cluster([container], rewrite=rewrite)
        ep = location.endpoint_for(endpoint)
        ep.publish(clstr, fqdns[0], ssl=cert)

    # wait until quit
    if args.i:
        interactive.stdin_loop(container)
    else:
        try:
            location.conn.wait_until_complete()
        except KeyboardInterrupt:
            pass
    return location


def main():
    maybe_location = main_impl()
    if maybe_location is not None:
        maybe_location.disconnect()


if __name__ == "__main__":
    main()
