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

from tfnz.cli import generic_cli, base_argparse
from tfnz.docker import Docker


def main():
    parser = base_argparse('tfcache')
    parser.add_argument('image', help='image UUID or tag to upload to cache')
    generic_cli(parser, {None: cache_image}, quiet=False)


def cache_image(location, args):
    descr = Docker.description(args.image)
    location.ensure_image_uploaded(args.image, descr=descr)


if __name__ == "__main__":
    main()
