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

import socket
import logging
import weakref


class Backchannel:
    """Creates a non-parallel tunnel from the given port inside the container (bound to localhost)"""

    def __init__(self, ctr, port, conn):
        self.ctr = weakref.ref(ctr)
        self.conn = weakref.ref(conn)
        self.port = port
        self.proc = None

        # connect to the local server
        logging.debug("Connecting backchannel to localhost, port: " + str(self.port))
        self.socket = socket.socket()
        self.fileno = self.socket.fileno()
        try:
            self.socket.connect(('127.0.0.1', self.port))
        except OSError as e:  # connection failed
            raise ValueError("Connection onto local server for backchannel failed on port: " + str(self.port))

        # create a proxy in the container ready to receive the connection
        self.proc = self.ctr().spawn_process('/usr/bin/socat TCP4-LISTEN:%d STDIO' % port,
                                             data_callback=self._from_remote,
                                             termination_callback=self._remote_proxy_closed)
        logging.info("Created remote proxy: " + str(self.port))

        # hook into the message queue now we actually can receive messages
        conn.loop.register_exclusive(self.fileno, self._from_local)

    def _from_remote(self, container, data):  # container is part of the callback, do not remove
        # Write the data
        # logging.debug("From backchannel (%s): %s\n%s" % (self.ctr().uuid.decode(), [hex(d) for d in data], data.decode()))
        self.socket.sendall(data)

    def _from_local(self, localfd):
        data = self.socket.recv(65536)
        #
        # # has the local server binned out?
        # if len(data) == 0:
        #     return
        #
        #     logging.debug("Disconnecting from localhost, port: " + str(self.port))
        #     self.conn().loop.unregister_exclusive(self.fileno)
        #     self.socket.close()
        #     self.socket = None
        #     self.fileno = None
        #
        #     logging.debug("Destroying proxy process")
        #     self.ctr().destroy_process(self.proc)
        #     self.proc = None
        #     return

        # logging.debug("To backchannel (%s): %s\n%s" % (self.ctr().uuid.decode(), [hex(d) for d in data], data.decode()))
        if self.proc is None:
            logging.warning("Tried to send on a backchannel but it had been closed remotely: " + data.decode())
        self.proc.stdin(data)

    def _remote_proxy_closed(self, msg):
        logging.debug("Remote proxy closed for port: " + str(self.port))
        self.conn().loop.unregister_exclusive(self.fileno)
        self.proc = None
