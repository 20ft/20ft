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
from typing import Optional
from . import Killable


class Process(Killable):
    """An object encapsulating a process within a container.
    Do not instantiate directly, use container.spawn_process."""
    def __init__(self, parent, uuid, data_callback, termination_callback, stderr_callback=None):
        super().__init__()
        self.parent = weakref.ref(parent)
        self.node = weakref.ref(parent.parent())
        self.location = weakref.ref(self.node().parent())
        self.conn = weakref.ref(parent.conn())
        self.uuid = uuid
        self.data_callback = data_callback
        self.termination_callback = termination_callback
        self.stderr_callback = stderr_callback
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
        self.ensure_alive()
        if len(data) == 0:
            self.destroy()
            return

        self.conn().send_cmd(b'stdin_process', {'node': self.node().pk,
                                                'container': self.parent().uuid,
                                                'process': self.uuid}, bulk=data)

    def destroy(self, with_command=True):
        if self.bail_if_dead():
            return

        # and then wait for notice of termination in msg.bulk
        if with_command:
            self.conn().send_cmd(b'destroy_process', {'node': self.node().pk,
                                                      'container': self.parent().uuid,
                                                      'process': self.uuid})
        logging.info("Terminated client side: %s" % self.uuid.decode())
        self.mark_as_dead()
        if self.termination_callback is not None:
            self.termination_callback(self, 0)

    def give_me_messages(self, msg):
        if self.bail_if_dead():
            return

        if msg is None:
            logging.error("give_me_messages was sent None")
            return

        # Has the process died?
        if len(msg.bulk) == 0:
            logging.info("Terminated server side: %s (%d)" % (self.uuid.decode(), msg.params['returncode']))
            self.mark_as_dead()
            if self.termination_callback is not None:
                self.location().call_on_main(self.termination_callback, (self, msg.params['returncode'],))
            return

        # Stderr?
        if 'stderr' in msg.params:
            if self.stderr_callback is not None:
                self.stderr_callback(self, msg.bulk)
            return

        # Otherwise we're just data
        if self.data_callback is not None:
            self.data_callback(self, msg.bulk)

    def __repr__(self):
        return "<Process '%s'>" % self.uuid.decode()
