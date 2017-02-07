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
import _thread
from . import Killable


class Process(Killable):
    """An object encapsulating a process within a container.
    Do not instantiate directly, use container.spawn_process."""
    def __init__(self, parent, uuid, data_callback, terminated_callback):
        super().__init__()
        self.parent = weakref.ref(parent)
        self.node = weakref.ref(self.parent().parent())
        self.conn = weakref.ref(self.parent().conn())
        self.data = b''
        self.uuid = uuid
        self.completed_lock = _thread.allocate_lock()
        self.reply_lock = _thread.allocate_lock()
        self.reply_data = None
        self.drop_next_reply = False
        self.data_callback = data_callback
        self.terminated_callback = terminated_callback
        self.completed_lock.acquire()
        logging.info("Created process: " + self.uuid)

    def internal_destroy(self, with_command=True):
        # Destroy this process
        if self.bail_if_dead():
            return
        self.mark_as_dead()

        if with_command:
            self.conn().send_cmd('destroy_process',
                                 params={'node': self.node().pk,
                                         'container': self.parent().uuid,
                                         'process': self.uuid})
        if self.terminated_callback is not None:
            self.terminated_callback(self)
        logging.info("Destroyed process: " + self.uuid)

    def stdin(self, data: bytes, return_reply=False, drop_echo=False):
        """Inject data into stdin for the process.

        :param data: The data to inject -  bytes, not a string.
        :param return_reply: Block and return the data from the next arriving message.
        :param drop_echo: The first reply is an echo of the input, so discard it.

        Note that because we are moving raw data, this may not behave as you expect. Remember to:

        * Turn strings into bytes with .encode()
        * Add '\\\\n' to emulate carriage return.
        * Turn returned bytes into strings with .decode()
        """
        self.ensure_alive()
        self.conn().send_cmd('stdin_process',
                             params={'node': self.node().pk,
                                     'container': self.parent().uuid,
                                     'process': self.uuid},
                             bulk=data)
        self.drop_next_reply = drop_echo
        if not return_reply:
            return

        # catching the reply
        self.reply_data = None
        self.reply_lock.acquire()
        # gets released by give_me_messages
        self.reply_lock.acquire()
        self.reply_lock.release()

        return self.reply_data

    def wait_until_complete(self) -> bytes:
        """Wait until the process is complete. If using default callback, returns all data collected."""
        self.ensure_alive()
        self.completed_lock.acquire()
        return self.data

    def give_me_messages(self, msg):
        if self.bail_if_dead():
            return

        # Has the process died?
        if len(msg.bulk) == 0:
            logging.info("Process terminated server side: " + self.uuid)
            self.mark_as_dead()
            if self.reply_lock.locked():  # it may be that there is no reply
                self.reply_lock.release()
            if self.terminated_callback is not None:
                self.terminated_callback(self)
            self.completed_lock.release()  # release the blocker
            return

        # dropping the echo?
        if self.drop_next_reply:
            self.drop_next_reply = False
            return

        # We take a locked temp_lock to mean we are trying to catch the reply
        if self.reply_lock.locked():
            self.reply_data = msg.bulk
            self.reply_lock.release()

        # Otherwise we're just data
        if self.data_callback is not None:
            self.data_callback(self, msg.bulk)
        else:
            self.data += msg.bulk

    def __repr__(self):
        return "<tfnz.process.Process object at %x (uuid=%s)>" % (id(self), self.uuid)
