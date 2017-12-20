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
    parser = base_argparse('tfdomains')
    subparsers = parser.add_subparsers(title='commands', dest='command')
    p_list = subparsers.add_parser('list', help='list domains')
    p_token = subparsers.add_parser('prepare', help='receive a pre-claim token')
    p_token.add_argument('prepare_domain', metavar='my.com')
    p_create = subparsers.add_parser('claim', help='claim a domain')
    p_create.add_argument('claim_domain', metavar='my.com')
    p_global = subparsers.add_parser('global', help='make a domain global')
    p_global.add_argument('global_domain', metavar='my.com')
    p_private = subparsers.add_parser('private', help='make a domain private')
    p_private.add_argument('private_domain', metavar='my.com')
    p_release = subparsers.add_parser('release', help='release your claim')
    p_release.add_argument('release_domain', metavar='my.com')

    generic_cli(parser, {'list': list_dom, 'prepare': prepare, 'claim': claim,
                         'private': private, 'global': gbl, 'release': release})


def list_dom(location, args):
    for dom in location.endpoints.values():
        print(dom.domain)


def prepare(location, args):
    rtn = location.conn.send_blocking_cmd(b'prepare_domain', {'domain': args.prepare_domain})
    print("Put a DNS record on your domain: tf-token.%s, TXT=%s" %
          (args.prepare_domain, rtn.params['token'].decode()))
    print("...then run: tfdomains claim " + args.prepare_domain)
    print("The request will time out (and become invalid) after six hours.")


def claim(location, args):
    location.conn.send_blocking_cmd(b'claim_domain', {'domain': args.claim_domain})
    print("Claimed successfully - you can remove the tf-token record from DNS")


def gbl(location, args):
    location.conn.send_blocking_cmd(b'make_domain_global', {'domain': args.global_domain})
    print("Domain made global, clients will need to re-attach to see the change")


def private(location, args):
    location.conn.send_blocking_cmd(b'make_domain_private', {'domain': args.private_domain})
    print("Domain made private, clients will need to re-attach to see the change but can no longer publish.")


def release(location, args):
    location.conn.send_blocking_cmd(b'release_domain', {'domain': args.release_domain})
    print("Released domain")


if __name__ == "__main__":
    main()
