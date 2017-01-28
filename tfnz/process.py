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

import weakref
import logging
from .waitable import Waitable


class Process(Waitable):
    """An object encapsulating a process within a container.
    Do not instantiate directly, use container.spawn_process."""
    def __init__(self, parent, uuid, data_callback, terminated_callback):
        super().__init__()
        self.parent = weakref.ref(parent)
        self.node = weakref.ref(self.parent().parent())
        self.conn = weakref.ref(self.parent().conn())
        self.data = b''
        self.uuid = uuid
        self.dead = False
        self.data_callback = data_callback
        self.terminated_callback = terminated_callback
        logging.info("Created process: " + self.uuid)

    def destroy(self):
        """Destroy this process."""
        # No good at destroying backgrounded processes
        if self.dead:
            return
        self.dead = True
        self.conn().send_cmd('destroy_process',
                             params={'node': self.node().pk,
                                     'container': self.parent().uuid,
                                     'process': self.uuid})
        self.is_ready()  # release the blocker
        if self.terminated_callback is not None:
            self.terminated_callback(self)

    def wait_until_complete(self):
        """Wait until the process is complete. If using default callback, returns all data collected."""
        if not self.wait_until_ready():
            raise ValueError("Process didn\'t complete: " + self.uuid)
        return self.data

    def give_me_messages(self, msg):
        if self.dead:
            return

        # Has the process died?
        length = len(msg.bulk)
        if len(msg.bulk) == 0:
            logging.info("Process terminated server side: " + self.uuid)
            self.dead = True
            self.is_ready()  # release the blocker
            if self.terminated_callback is not None:
                self.terminated_callback(self)
                return

        # Otherwise we're just data
        if self.data_callback is not None:
            self.data_callback(self, msg.bulk)
        else:
            self.data += msg.bulk
