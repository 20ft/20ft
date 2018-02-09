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

import weakref
import logging
import os.path
from . import Taggable


class Volume(Taggable):
    def __init__(self, location, uuid, tag):
        super().__init__(location.user_pk, uuid, tag)
        # Do not construct directly, use Location.create_volume
        self.connection = weakref.ref(location.conn)

    def snapshot(self):
        """Mark the current state of the volume as being it's initial state."""
        self.connection().send_cmd(b'snapshot_volume', {'volume': self.uuid})
        logging.info("Set snapshot for volume: " + self.uuid.decode())

    def rollback(self):
        """Resets the volume back to the initial state."""
        self.connection().send_cmd(b'rollback_volume', {'volume': self.uuid})
        logging.info("Rolled back to snapshot: " + self.uuid.decode())

    @staticmethod
    def trees_intersect(current, proposed):
        # ensure the proposed directory is neither a subdir nor a superdir of any existing directories
        p = os.path.abspath(proposed)
        for cur in current:
            c = os.path.abspath(cur)
            if len(p) > len(c):
                if p[:len(c)] == c:
                    return p, c  # p is a subtree of c
            else:
                if c[:len(p)] == p:
                    return c, p  # c is a subtree of p
        return None

    def __repr__(self):
        return "<Volume '%s'>" % self.namespaced_display_name()
