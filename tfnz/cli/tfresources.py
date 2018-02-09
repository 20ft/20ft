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

import json
from base64 import b64encode
from tfnz.cli import generic_cli, base_argparse


def main():
    parser = base_argparse('tfresources')
    generic_cli(parser, {None: list_resources})


def list_resources(location, args):
    resources = {
        'location': location.location,
        'nodes': {b64encode(node.pk).decode(): node.stats for node in location.nodes.values()},
        'volumes': [vol.namespaced_display_name() for vol in location.volumes.values()],
        'endpoints': [ep.domain for ep in location.endpoints.values()]
    }

    print(json.dumps(resources, indent=2))


if __name__ == "__main__":
    main()
