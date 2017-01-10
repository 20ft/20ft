"""Copyright (c) 2017 David Preece, All rights reserved.

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

import os
from base64 import b64encode, b64decode
from libnacl.public import SecretKey


class KeyPair:
    """Holds a public/secret key pair as base 64"""

    def __init__(self, name=None, prefix='~/.20ft'):
        self.public = None
        self.secret = None
        if name is None:
            return

        # we are also fetching the keys
        expand = os.path.expanduser(prefix)
        try:
            with open(expand + '/' + name + ".pub", 'rb') as f:
                self.public = str(f.read(), 'ascii')[:-1]
        except FileNotFoundError:
            raise RuntimeError("No public key found, halting")
        try:
            with open(expand + '/' + name, 'rb') as f:
                self.secret = str(f.read(), 'ascii')[:-1]
        except FileNotFoundError:
            pass

    def public_binary(self):
        return b64decode(self.public)

    def secret_binary(self):
        return b64decode(self.secret)

    @staticmethod
    def new():
        """Create a new random key pair"""
        keys = SecretKey()
        rtn = KeyPair()
        rtn.public = str(b64encode(keys.pk), 'ascii')
        rtn.secret = str(b64encode(keys.sk), 'ascii')
        return rtn

    def __repr__(self):
        return "<tfnz.Keys object at %x (pk=%s)>" % (id(self), self.public)
