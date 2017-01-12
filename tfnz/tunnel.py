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

# A note on nomenclature
# A tunnel logically goes from localhost:port to container:port but has no TCP connections
# The tunnel is made from zero or more proxies which do the actual tunnelling

import logging
import socket
import time
import shortuuid
from .waitable import Waitable


class Tunnel(Waitable):
    """An object representing a TCP proxy from localhost onto a container.
    Do not instantiate directly, use location.tunnel_onto, location.wait_http_200 or location.browser_onto.

    Nothing end user callable - interact with the proxy through TCP (or call localport if you didn't set it explicitly).
    Note that apparently plaintext traffic through the tunnel is still encrypted on the wire."""

    def __init__(self, connection, node, container, port, localport, bind):
        super().__init__()
        # tell the location what we want
        self.uuid = shortuuid.uuid().encode('ascii')
        self.node = node
        self.connection = connection
        self.container = container
        self.port = port
        self.localport = localport
        self.bind = bind
        self.fd = None
        self.proxies = {}

    def connect(self):
        # create the listen socket
        self.socket = socket.socket()
        self.socket.setblocking(False)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.bind(("127.0.0.1" if self.bind is None else self.bind, self.localport))
        except OSError:
            pass
        self.socket.listen()
        self.fd = self.socket.fileno()
        self.connection.loop.register_fd_socket(self.fd, self.event)

        # have the node create it's end.
        # don't make this call earlier or we get a textbook race condition
        logging.debug("Creating tunnel: " + str(self.uuid))
        self.connection.send_cmd(b'create_tunnel',
                                 {'tunnel': str(self.uuid, 'ascii'),
                                  'node': str(self.node.pk, 'ascii'),
                                  'container': str(self.container.uuid, 'ascii'),
                                  'port': self.port})

    def tunnel_up(self, msg):
        # and the proxies (are socket instances referred to by their fileno)
        logging.info("Created tunnel object onto: %s (%d -> %d)" %
                     (str(self.uuid, 'ascii'), self.localport, self.port))
        self.is_ready()

    def destroy(self):
        """Destroy this tunnel."""
        if not self.socket:
            logging.debug("Second attempt to destroy a tunnel (no biggie)")
            return
        for proxy in list(self.proxies.items()):
            self.connection.loop.unregister_fd_socket(proxy[0])
            proxy[1].close()
        self.proxies.clear()
        self.connection.loop.unregister_fd_socket(self.fd)
        self.socket.close()
        self.socket = None
        self.connection.send_cmd(b'destroy_tunnel', params={"tunnel": str(self.uuid, 'ascii')})
        logging.info("Destroyed tunnel: " + str(self.uuid, 'ascii'))

    def event(self, event):
        # An event on the connection itself
        # The accept call sometimes fails
        new_proxy = None
        while new_proxy is None:
            try:
                new_proxy = self.socket.accept()
            except BlockingIOError:
                logging.warning("Attempting to accept a new connection but the resource was temporarily unavailable")
                time.sleep(0.1)

        fd = new_proxy[0].fileno()
        self.proxies[fd] = new_proxy[0]
        self.connection.loop.register_fd_socket(fd, self.to_proxy)
        logging.debug("Accepted proxy connection, fd: " + str(fd))

    def to_proxy(self, event):
        # Send to the location which will forward to the end client.
        self.wait_until_ready()
        if event[1] == 5:  # poll says this socket needs to be closed
            logging.debug("Sending client initiated proxy close: " + str(event[0]))
            self.close_proxy(event[0])
            self.connection.send_cmd(b'close_proxy', params={"tunnel": str(self.uuid, 'ascii'),
                                                             "proxy": event[0]})
            return

        if event[1] == 4:  # actually closed
            logging.debug("Unregistering fd socket due to event 4: " + str(event[0]))
            self.connection.loop.unregister_fd_socket(event[0])
            return

        try:
            data = self.proxies[event[0]].recv(131072)
            logging.debug("Sending data to proxy: " + str(event[0]))
            self.connection.send_cmd(b'to_proxy', params={"tunnel": str(self.uuid, 'ascii'),
                                                          "proxy": event[0]}, bulk=data)
        except KeyError:
            logging.warning("Received an event for a no-longer existent proxy: " + str(event[0]))

        return True  # everything went fine

    def from_proxy(self, msg):
        # Data being sent from the container
        try:
            proxy_fd = msg.params['proxy']
        except KeyError:
            # a blank message with no proxy id is to let us know it constructed server side
            logging.debug("From proxy message with no proxy, marking tunnel as ready: " + str(self.uuid, 'ascii'))
            return

        if msg.command == b'close_proxy':
            logging.debug("Server told us to close connection: " + str(proxy_fd))
            self.close_proxy(proxy_fd)
            return

        try:
            skt = self.proxies[proxy_fd]
            skt.sendall(msg.bulk)
        except KeyError:
            pass  # proxy has already gone away

    def close_proxy(self, fd):
        # Close one single proxy
        try:
            self.proxies[fd].close()
            del self.proxies[fd]
            logging.debug("Closed proxy connection, fd: " + str(fd))
        except KeyError:
            pass  # proxy has already gone away

    def __repr__(self):
        return "<tfnz.Tunnel object at %x (container-uuid=%s port=%d)>" % \
               (id(self), self.container.uuid, self.port)
