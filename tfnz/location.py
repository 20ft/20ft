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

import logging
import io
import random
import sys
import traceback
import webbrowser
import socket
import requests
import time
import os
from requests.exceptions import ConnectionError
from subprocess import check_output, call, DEVNULL
from .waitable import Waitable
from .node import Node
from .connection import Connection
from .send import Sender
from .tunnel import Tunnel
from .container import Container


# A NOTE ON STR VS BYTES
# Anything that refers to anything i.e. a uuid are stored and used only as bytes
# Everything else (including public keys) are strings
# The message class translates into the correct types on reception but will take only strings for send (a json thing)
# Long running conversations (i.e. from a process back to the client) are identified by message uuid's

file_not_found_text = """
There is no ~/.20ft/default_location so cannot choose default location.
Either write the fqdn of the default location into ~/.20ft/default_location or pass explicitly.
"""


class Location(Waitable):
    """The root location object.

        :param location: An optional fqdn of the location (i.e. tiny.20ft.nz).
        :param location_ip: A optional explicit ip for the broker.
        :param deubg_log: Optionally configure Python logging. True/False to select debug/info logging levels."""

    def __init__(self, location: str=None, location_ip: str=None, debug_log: bool=None):
        super().__init__()

        # set up logging
        if debug_log is not None:
            logging.basicConfig(level=logging.DEBUG if debug_log else logging.INFO,
                                format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
                                datefmt='%m%d%H%M%S')

        # find the default location
        if location is None:
            try:
                with open(os.path.expanduser('~/.20ft/default_location'), 'r') as f:
                    location = f.read().strip('\n')
            except FileNotFoundError:
                raise ValueError(file_not_found_text)
        self.location = location

        self.nodes = {}
        self.last_best_nodes = None
        self.last_best_node_idx = None
        self.tunnels = {}
        self.conn = Connection(location, location_ip=location_ip)
        self.conn.register_commands(self, Location._commands)
        self.send = None
        self.conn.start()

    def ensure_image_uploaded(self, docker_image_id: str):
        """Sends missing docker layers to the location.

        :param docker_image_id: use the short form id or name:tag

        This is not a necessary step and is implied when spawning a container unless specifically disabled.
        The layers are uploaded on a background thread."""
        self.wait_until_ready()

        logging.info("Ensuring layers are uploaded for: " + docker_image_id)

        # See if we have it locally
        try:
            Sender.layer_stack(docker_image_id)
        except RuntimeError:
            logging.info("Fetching with 'docker pull' (may take some time): " + docker_image_id)
            if call(['/usr/local/bin/docker', 'pull', docker_image_id], stdout=DEVNULL, stderr=DEVNULL) != 0:
                raise ValueError("Could not docker pull image: " + docker_image_id)

        Sender(self.conn, docker_image_id).send()

    def ranked_nodes(self, bias_memory: bool=True) -> [Node]:
        """Ranks the nodes in order of cpu or memory availability.

        :param bias_memory: prioritise memory availability over cpu.
        :returns: a list of node objects.

        Not a necessary step but useful if you wish to explicitly schedule containers on the same node.
        The output of best_node is affected by the cpu/memory bias.
        Note that the difference in processor performance is accounted for and is measured in passmarks."""
        self.wait_until_ready()
        nodes = list(self.nodes.values())
        if bias_memory:
            self.last_best_nodes = sorted(nodes, key=lambda node: node.stats['memory'], reverse=True)
        else:
            self.last_best_nodes = sorted(nodes, key=lambda node: node.stats['cpu'], reverse=True)
        self.last_best_node_idx = None
        return self.last_best_nodes

    def best_node(self) -> Node:
        """Choose the currently best node to launch a container on.

        :returns: a Node object or None.

        Iterates over the list of nodes to aid with load balancing.
        For explicit control use ranked_nodes."""
        # initialise if we need to
        self.wait_until_ready()
        if self.last_best_nodes is None:
            self.ranked_nodes()
        if self.last_best_node_idx is None:
            self.last_best_node_idx = 0

        # maybe there are no nodes at all
        if len(self.last_best_nodes) == 0:
            raise ValueError("Cannot choose best node when there are no nodes in this location.")

        # get a result, then
        rtn = self.last_best_nodes[self.last_best_node_idx]

        # next node
        self.last_best_node_idx += 1
        if self.last_best_node_idx >= len(self.nodes):
            self.last_best_node_idx = 0

        return rtn

    def tunnel_onto(self, container: Container, port: int, localport: int=0, bind: str=None) -> Tunnel:
        """Creates a TCP proxy between localhost and a container.

        :param container: The container object.
        :param port: The TCP port on the container to connect to.
        :param localport: Optional choice of local port no.
        :param bind: Optionally bind to an address other than localhost.
        :returns: A Tunnel object.

        This call does no checking to ensure the server side is ready -
        but a failed connection will not destroy the tunnel itself and hence it can be used for polling.
        If the optional port number is left as default, one will be automatically chosen
        (and set as .localport on the created Tunnel).
        """
        self.wait_until_ready()
        container.wait_until_ready()
        if localport == 0:
            localport = Location.find_unused_local_port()

        # create the tunnel
        container.wait_until_ready()  # otherwise the IP address may not exist on the node and creation will fail
        tunnel = Tunnel(self.conn, container.parent(), container, port, localport, bind)
        self.tunnels[tunnel.uuid] = tunnel
        tunnel.connect()  # connection done 'late' so we can get the tunnel into tunnels first
        return tunnel

    def browser_onto(self, container, dest_port: int=80, fqdn: str='127.0.0.1', path: str='',
                     actual_browser: bool=True) -> Tunnel:
        """Attaches a web browser onto port 80 of the passed container.

        :param container: A Container object.
        :param dest_port: Override the default port.
        :param fqdn: A host name to use in the http request.
        :param path: A path on the server - appended to /
        :returns: A Tunnel object.

        Note that webservers running virtual hosts need to be connected to with a hostname - hence passing the fqdn.
        If you're testing a (for example) CMS and keep getting the default page, you probably need to set this.
        Note that you will need to locally set that fqdn to resolve to 127.0.0.1. See tf.py for an example.

        Connection attempts are 2/sec for 30 seconds"""

        # some checks
        addr = socket.gethostbyname(fqdn)
        if addr != '127.0.0.1':
            raise ValueError("FQDN '%s' does not resolve to localhost" % fqdn)

        # OK
        tnl = self.tunnel_onto(container, dest_port)
        tnl.wait_until_ready()
        url = 'http://%s:%d/%s' % (fqdn, tnl.localport, path if path is not None else '')

        # poll until it's alive
        attempts_remaining = 60
        while True:
            try:
                r = requests.get(url)
                if r.status_code == 200:
                    logging.info("Connected onto: " + url)
                    break
            except ConnectionError:
                pass
            attempts_remaining -= 1
            if attempts_remaining == 0:
                raise ValueError("Could not connect to: " + url)
            time.sleep(0.5)

        # connect a browser
        if actual_browser:
            webbrowser.open_new(url)

        return tnl

    def wait_http_200(self, container, dest_port: int=80,
                      fqdn: str='127.0.0.1', path: str='') -> Tunnel:
        """Exactly the same as browser_onto except does not spawn the browser."""
        logging.info("Waiting on http 200: " + str(container.uuid, 'ascii'))
        return self.browser_onto(container, dest_port, fqdn, path, actual_browser=False)

    def destroy_tunnel(self, tunnel: Tunnel):
        """Destroy a tunnel"""
        tunnel.destroy()
        del self.tunnels[tunnel.uuid]

    def _tunnel_up(self, msg):
        self.tunnels[msg.uuid].tunnel_up(msg)

    def _from_proxy(self, msg):
        self.tunnels[msg.uuid].from_proxy(msg)

    def _close_proxy(self, msg):
        self.tunnels[msg.uuid].close_proxy(msg.params['proxy'])

    def _resource_offer(self, msg):
        logging.debug("Location has sent resource offer")
        self.is_ready()

        # the list of available nodes
        if 'nodes' in msg.params:
            nodes = list(msg.params['nodes'])
            if len(nodes) == 0:
                logging.warning("The list of resources did not include any nodes, can't run code at this location.")
            else:
                for node in nodes:
                    description = list(node.items())[0]
                    pk = description[0].encode('ascii')
                    resource_values = description[1]
                    self.nodes[pk] = Node(self, pk, self.conn, resource_values)

    def _log(self, msg):
        if msg.params['error']:
            logging.error("---> " + msg.params['log'])
        else:
            logging.info("---> " + msg.params['log'])

    def _kicked(self, msg):
        logging.critical("Another instance of this account has connected.")
        raise KeyboardInterrupt

    @staticmethod
    def find_unused_local_port() -> int:
        # find the used ports
        out = io.BytesIO(check_output(['/usr/sbin/netstat', '-n', '-f', 'inet', '-p', 'tcp']))
        out.readline()
        out.readline()
        ports = set()
        for line in out:
            try:
                props = line.split()
                ip_bits = str(props[3], 'ascii').split('.')
                ports.add(ip_bits[4])
            except:
                raise RuntimeError("Failed trying to find an open local port")

        # keep guessing until we get an empty one
        while True:
            candidate = random.randrange(1025, 8192)
            if candidate not in ports:
                return candidate

    _commands = {b'resource_offer': (_resource_offer, [], False),
                 b'tunnel_up': (_tunnel_up, [], False),
                 b'from_proxy': (_from_proxy, ['proxy'], False),
                 b'close_proxy': (_close_proxy, ['proxy'], False),
                 b'log': (_log, ['error', 'log'], False),
                 b'kicked': (_kicked, [], False)}

    def __repr__(self):
        return "<tfnz.Location object at %x (nodes=%d)>" % (id(self), len(self.nodes))


# misc

def last_image() -> str:
    """Finding the most recent docker image on this machine.

       The intent is that last_image can be used as part of a development cycle (pass as image to spawn)."""
    dkr_result = check_output(['docker', 'images', '-q'])
    if dkr_result == b'':
        raise ValueError("Docker has no local images.")
    return str(dkr_result[:12], 'ascii')


def uncaught_exception(exctype, value, tb):
    if exctype is KeyboardInterrupt:
        logging.info("Caught Ctrl-C, closing")  # clearing server side objects done by server
        exit(0)
    traceback.print_exception(exctype, value, tb)
    exit(1)

sys.excepthook = uncaught_exception
