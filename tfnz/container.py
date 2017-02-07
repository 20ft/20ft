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
import json
import weakref
import requests_unixsocket
from . import Waitable, Killable
from .tunnel import Tunnel
from .process import Process

requests_unixsocket.monkeypatch()


class Container(Waitable, Killable):
    """An object representing a single container. Do not instantiate directly, use node.spawn."""
    def __init__(self, parent, image: str, uuid: str, docker_config: dict=None, env: dict=None):
        Waitable.__init__(self)
        Killable.__init__(self)
        self.parent = weakref.ref(parent)
        self.location = weakref.ref(self.parent().parent())
        self.conn = weakref.ref(self.parent().conn())
        self.image = image
        self.uuid = uuid
        self.processes = {}
        self.docker_config = docker_config
        self.env = env
        self._ip = None
        self.allowed_to_connect = set()

    def internal_destroy(self):
        # Destroy this container
        if self.bail_if_dead():
            return
        self.wait_until_ready()
        self.mark_as_dead()

        # Fake the processes being destroyed (they will be anyway)
        for proc in list(self.processes.values()):
            proc.internal_destroy(with_command=False)

        # Disconnect
        self.conn().send_cmd('destroy_container',
                             {'node': self.parent().pk,
                              'container': self.uuid})
        logging.info("Destroyed container: " + self.uuid)

    def ip(self) -> str:
        """Return this container's internal IP address"""
        self.ensure_alive()
        self.wait_until_ready()
        return self._ip

    def attach_tunnel(self, dest_port: int, localport: int=None, bind: str=None) -> Tunnel:
        """Creates a TCP proxy between localhost and a container.

        :param dest_port: The TCP port on the container to connect to.
        :param localport: Optional choice of local port no.
        :param bind: Optionally bind to an address other than localhost.
        :returns: A Tunnel object.

        This call does no checking to ensure the server side is ready -
        but a failed connection will not destroy the tunnel itself and hence it can be used for polling.
        If the optional port number is left as default, one will be automatically chosen.
        """
        self.ensure_alive()
        return self.location().tunnel_onto(self, dest_port, localport, bind)

    def attach_browser(self, dest_port: int=80, fqdn: str='localhost', path: str='') -> Tunnel:
        """Attaches a web browser onto port 80 of the container.

        :param dest_port: Override the default destination port.
        :param fqdn: A host name to use in the http request.
        :param path: A path on the server - appended to /
        :returns: A Tunnel object.

        Note that webservers running virtual hosts need to be connected to with a hostname - hence passing the fqdn.
        If you're testing a (for example) CMS and keep getting the default page, you probably need to set this.
        Note that you will need to locally set that fqdn to resolve to 127.0.0.1. See tf for an example.

        Connection attempts are 2/sec for 30 seconds"""
        self.ensure_alive()
        return self.location().browser_onto(self, dest_port, fqdn, path, True)

    def wait_http_200(self, dest_port: int=80, fqdn: str='localhost', path: str='') -> Tunnel:
        """Poll until an http 200 is returned.

        :param dest_port: Override the default port.
        :param fqdn: A host name to use in the http request.
        :param path: A path on the server - appended to /
        :returns: A Tunnel object.

        Same notes as for 'attach_browser'."""
        self.ensure_alive()
        return self.location().browser_onto(self, dest_port, fqdn, path, False)

    def destroy_tunnel(self, tunnel: Tunnel):
        """Destroy a tunnel

        :param tunnel: The tunnel to be destroyed."""
        self.ensure_alive()
        self.location().destroy_tunnel(tunnel)

    def all_tunnels(self) -> [Tunnel]:
        """Returns all the tunnels connected to this container"""
        self.ensure_alive()
        return list(self.location().tunnels.values())

    def allow_connection_from(self, container):
        """Allow another container to call this one over ipv4

        :param container: The container that will be allowed to call.

        If the passed container is already allowed to connect, this is a no-op."""
        self.ensure_alive()
        self.wait_until_ready()
        if container in self.allowed_to_connect or container is self:
            logging.warning("Container is already allowed to connect")
            return

        self.conn().send_cmd('allow_connection', {'node': self.parent().pk,
                                                  'container': self.uuid,
                                                  'ip': container.ip()})
        self.allowed_to_connect.add(container)
        logging.info("Allowed connection (from %s) on: %s" % (container.uuid, self.uuid))

    def disallow_connection_from(self, container):
        """Stop allowing another container to call this one over ipv4

        :param container: The container that will no longer be allowed to call.

        If the passed container is already not allowed to connect, this is a no-op."""
        self.ensure_alive()
        if container not in self.allowed_to_connect:
            logging.warning("Container is already not allowed to connect")
            return

        self.conn().send_cmd('disallow_connection', {'node': self.parent().pk,
                                                     'container': self.uuid,
                                                     'ip': container.ip()})
        self.allowed_to_connect.remove(container)
        logging.info("Disallowed connection (from %s) on: %s" % (container.uuid, self.uuid))

    def all_allowed_connections(self) -> []:
        """Returns all the containers that are allowed to connect to this one"""
        self.ensure_alive()
        return list(self.allowed_to_connect)

    def spawn_process(self, remote_command, data_callback=None, termination_callback=None) -> Process:
        """Spawn a process within a container, receives data asynchronously via a callback.

        :param remote_command: The process to remotely launch.
        :param data_callback: A callback for arriving data - signature (object, bytes)
        :param termination_callback: For when the process completes - signature (object)
        :return: A Process object.

        Note that the command can be either the string ("ps faxu") format or list (["ps", "faxu"]) format."""
        self.ensure_alive()
        self.wait_until_ready()

        # Cool, go.
        if isinstance(remote_command, str):
            remote_command = [remote_command]
        logging.info("Container (%s) spawning process: %s" % (self.uuid, json.dumps(remote_command)))

        # get the node to launch the process for us
        # we need the uuid of the spawn command because it's used to indicate when the process has terminated
        spawn_command_uuid = self.conn().send_cmd('spawn_process',
                             {'node': self.parent().pk,
                              'container': self.uuid,
                              'command': remote_command}, reply_callback=self._process_callback)
        rtn = Process(self, spawn_command_uuid, data_callback, termination_callback)
        self.processes[spawn_command_uuid] = rtn
        return rtn

    def spawn_shell(self, data_callback=None, termination_callback=None) -> Process:
        """Spawn a shell within a container, receives data asynchronously via a callback.

                :param data_callback: A callback for arriving data - signature (object, bytes)
                :param termination_callback: For when the process completes - signature (object)
                :return: A Process object.

                Use Container.destroy_process to destroy object."""
        self.ensure_alive()
        self.wait_until_ready()

        # get the node to launch the process for us
        # we need the uuid of the spawn command because it's used to indicate when the process has terminated
        spawn_command_uuid = self.conn().send_cmd('spawn_process',
                             {'node': self.parent().pk,
                              'container': self.uuid}, reply_callback=self._process_callback)
        rtn = Process(self, spawn_command_uuid, data_callback, termination_callback)
        self.processes[spawn_command_uuid] = rtn
        return rtn

    def destroy_process(self, process: Process):
        """Destroy a process

        :param process: The process to be destroyed."""
        self.ensure_alive()
        if process not in self.processes.values():
            raise ValueError("Process does not belong to this container")
        process.internal_destroy()
        del self.processes[process.uuid]

    def all_processes(self) -> [Process]:
        """Returns all the processes (that were manually launched) running on this container."""
        self.ensure_alive()
        return self.processes.values()

    def fetch(self, filename: str) -> bytes:
        """Fetch a single file from the container.

        :param: filename: The full-path name of the file to be retrieved.
        :return: the contents of the file as a bytes object.

        Since the file gets loaded into memory, this is probably not the best way to move large files."""
        self.ensure_alive()
        self.wait_until_ready()
        return self.conn().send_blocking_cmd('fetch',
                                             {'node': self.parent().pk,
                                              'container': self.uuid,
                                              'filename': filename}).bulk

    def put(self, filename: str, data: bytes):
        """Put a file into the container.

        :param: filename: The full-path name of the file to be placed.
        :param: data: The contents of the file as a bytes object.

        This will just overwrite so be careful. Note that new file paths are created on demand.
        """
        self.ensure_alive()
        self.wait_until_ready()
        self.conn().send_blocking_cmd('put',
                                      {'node': self.parent().pk,
                                       'container': self.uuid,
                                       'filename': filename}, bulk=data)

    def logs(self) -> [dict]:
        """Fetches the stdout log from the container.

        :return: A list of dictionary objects.

        The dictionary keys are:

        * log - a single log item.
        * stream - the stream it was received on.
        * time - the server timestamp when the message was logged."""
        self.ensure_alive()
        self.wait_until_ready()
        raw = self.conn().send_blocking_cmd('fetch_log',
                                           {'node': self.parent().pk,
                                            'container': self.uuid}).bulk
        lines = str(raw, 'utf-8').split('\n')
        return [json.loads(line) for line in lines if line != '']

    def _process_callback(self, msg):
        if self.bail_if_dead():
            return

        # we have to use message id to identify the container because it's needed to create a long running conversation
        # obituary?
        if msg.command == '' and msg.params == {} and msg.bulk == 'no_more_replies':
            logging.info("Process terminated: " + msg.uuid)
            del self.processes[msg.uuid]
            return

        # normal arrival of data
        if msg.uuid not in self.processes:
            logging.debug("Message arrived for an unknown process: " + msg.uuid)
            return

        logging.debug("Received data from process: " + msg.uuid)
        self.processes[msg.uuid].give_me_messages(msg)

    def __repr__(self):
        return "<tfnz.container.Container object at %x (image=%s uuid=%s)>" % (id(self), self.image, self.uuid)

