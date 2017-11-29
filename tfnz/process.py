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
from . import Killable


class Process(Killable):
    """An object encapsulating a process within a container.
    Do not instantiate directly, use container.spawn_process."""
    def __init__(self, parent, uuid, data_callback, termination_callback):
        super().__init__()
        self.parent = weakref.ref(parent)
        self.node = weakref.ref(parent.parent())
        self.conn = weakref.ref(parent.conn())
        self.uuid = uuid
        self.data_callback = data_callback
        self.termination_callback = termination_callback
        self.wrapper = None

    def stdin(self, data: bytes):
        """Inject data into stdin for the process.

        :param data: The data to inject -  bytes, not a string.

        Note that because this injects raw data, it may not behave as you expect. Remember to:

        * Turn strings into bytes with .encode()
        * Add '\\\\n' to emulate carriage return.
        * Turn returned bytes into strings with .decode()

        """
        # a client side disconnection?
        if len(data) == 0:
            self._internal_destroy()
            return

        self.ensure_alive()
        self.conn().send_cmd(b'stdin_process', {'node': self.node().pk,
                                                'container': self.parent().uuid,
                                                'process': self.uuid}, bulk=data)

    def _internal_destroy(self, with_command=True):
        # Destroy this process
        if self.bail_if_dead():
            return
        self.mark_as_dead()

        # Are we actually going to destroy it or is this a fake termination because the container has died?
        if with_command:
            self.conn().send_cmd(b'destroy_process', {'node': self.node().pk,
                                                      'container': self.parent().uuid,
                                                      'process': self.uuid})

        if self.termination_callback is not None:
            self.termination_callback(self)
        logging.info("Destroyed process: " + str(self.uuid))

    def _give_me_messages(self, msg):
        if self.bail_if_dead():
            return

        # Has the process died?
        if len(msg.bulk) == 0:
            logging.info("Terminated server side: " + str(self.uuid))
            self._internal_destroy(with_command=False)
            return

        # Otherwise we're just data
        if self.data_callback is not None:
            self.data_callback(self, msg.bulk)

    def __repr__(self):
        return "<tfnz.process.Process object at %x (uuid=%s)>" % (id(self), str(self.uuid))
