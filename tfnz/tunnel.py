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

# A note on nomenclature
# A tunnel logically goes from localhost:port to container:port but has no TCP connections
# The tunnel is made from zero or more proxies which do the actual tunnelling

import logging
import socket
import time
import shortuuid
from . import Killable


class Tunnel(Killable):
    """An object representing a TCP proxy from localhost onto a container.
    Do not instantiate directly, use location.tunnel_onto or location.wait_http_200.

    Interact with the proxy through TCP (or call localport if you didn't set it explicitly).
    Note that apparently plaintext traffic through the tunnel is still encrypted on the wire."""

    def __init__(self, connection, node, container, port, lp=None, bind=None, timeout=30):
        super().__init__()
        # tell the location what we want
        self.uuid = shortuuid.uuid().encode()
        self.sess = connection.rid
        self.node = node
        self.connection = connection
        self.socket = None
        self.container = container
        self.port = port
        self.lp = lp
        self.bind = bind
        self.fd = None
        self.timeout = timeout
        self.proxies = {}
        connection.register_connect_callback(self.session_reconnected)

    def __del__(self):
        self.destroy()  # bails if destroyed already

    def session_reconnected(self, rid):
        logging.debug("Tunnel reset its session id: " + str(self.uuid))
        self.sess = rid

    def connect(self):
        self.ensure_alive()
        # create the listen socket
        self.socket = socket.socket()
        self.socket.setblocking(False)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.bind(('0.0.0.0' if self.bind is None else self.bind, 0 if self.lp is None else self.lp))
            self.lp = self.socket.getsockname()[1]
        except OSError:
            pass
        self.socket.listen()
        self.fd = self.socket.fileno()
        self.connection.loop.register_exclusive(self.fd, self.event, comment="listener for " + str(self))

        # have the location create its end.
        self.connection.send_cmd(b'create_tunnel',
                                 {'container': self.container.uuid,
                                  'port': self.port,
                                  'timeout': self.timeout}, uuid=self.uuid)
        logging.info("Created tunnel object: %s (%d -> %d)" % (str(self.uuid), self.lp, self.port))

    def localport(self) -> int:
        """Returns the (possibly dynamically allocated) local port number.

        :return: the port number as an int"""
        self.ensure_alive()
        return self.lp

    def destroy(self):
        # Destroy this tunnel.
        if self.bail_if_dead():
            return
        self.mark_as_dead()
        self.connection.unregister_connect_callback(self.session_reconnected)

        for proxy in list(self.proxies.items()):
            self.connection.loop.unregister_exclusive(proxy[0])
            proxy[1].close()
        self.proxies.clear()
        self.connection.loop.unregister_exclusive(self.fd)
        self.socket.close()
        self.socket = None
        self.connection.send_cmd(b'destroy_tunnel', {"tunnel": self.uuid})
        logging.info("Destroyed tunnel: " + str(self.uuid))

    def event(self, localfd):
        # An event on the connection itself
        # The accept call sometimes fails
        if self.bail_if_dead():
            return
        new_proxy = None
        while new_proxy is None:
            try:
                new_proxy = self.socket.accept()
            except BlockingIOError:
                logging.debug("Attempting to accept a new connection but the resource was temporarily unavailable")
                time.sleep(0.1)

        fd = new_proxy[0].fileno()
        self.proxies[fd] = new_proxy[0]
        self.connection.loop.register_exclusive(fd, self.to_proxy, comment="proxy fd=" + str(fd))

        # send nothing to force the connection open on the far end - some servers like to talk first
        self.connection.send_cmd(b'to_proxy', {"tunnel": self.uuid,
                                               "proxy": fd}, bulk=b'')

        logging.debug("Accepted proxy connection, fd: " + str(fd))

    def to_proxy(self, localfd):
        # Send to the location which will forward to the end client.
        if self.bail_if_dead():
            return
        try:
            data = b''
            try:
                data = self.proxies[localfd].recv(8192)
            except ConnectionResetError:
                logging.debug("Connection reset when receiving from proxy")
                pass
            if data == b'':
                logging.debug("Received no data, assuming socket was closed for proxy: " + str(localfd))
                self.close_proxy(localfd)
                self.connection.send_cmd(b'close_proxy', {"tunnel": self.uuid,
                                                          "proxy": localfd})
            else:
                logging.debug("Sending data to proxy: " + str(localfd))
                self.connection.send_cmd(b'to_proxy', {"tunnel": self.uuid,
                                                       "proxy": localfd}, bulk=data)
        except KeyError:
            logging.debug("Received a forwarding request to a proxy not in map: " + str(localfd))

        return True  # everything went fine

    def from_proxy(self, msg):
        # Data being sent from the container
        if self.bail_if_dead():
            return
        try:
            proxy_fd = msg.params['proxy']
        except KeyError:
            # a blank message with no proxy id is to let us know it constructed server side
            logging.debug("From proxy message with no proxy, marking tunnel as ready: " + str(self.uuid))
            return

        if msg.command == 'close_proxy':
            logging.debug("Server told us to close connection: " + str(proxy_fd))
            self.close_proxy(proxy_fd)
            return

        try:
            skt = self.proxies[proxy_fd]
            skt.sendall(msg.bulk)
        except KeyError:
            pass  # proxy has already gone away

    def close_proxy(self, msg_or_fd):
        if self.bail_if_dead():
            return
        # Close one single proxy
        try:
            try:
                fd = msg_or_fd.params['proxy']
            except AttributeError:
                fd = msg_or_fd  # when we close the proxy locally we will have been passed a file desriptor
            self.proxies[fd].close()
            self.connection.loop.unregister_exclusive(fd)
            del self.proxies[fd]
            logging.debug("Closed proxy connection, fd: " + str(fd))
        except KeyError:
            pass  # proxy has already gone away

    def __repr__(self):
        return "<tfnz.tunnel.Tunnel object at %x (uuid=%s port=%d)>" % \
               (id(self), str(self.uuid), self.port)
