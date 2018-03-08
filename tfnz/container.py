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

import logging
import shortuuid
import weakref
from typing import Optional, List, Union, Callable, Any, Tuple
from . import Waitable, Killable, Connectable
from .tunnel import Tunnel
from .process import Process
from .ssh import SshServer


class Container(Waitable, Killable, Connectable):
    """An object representing a single container. Do not instantiate directly, use node.spawn."""
    def __init__(self, parent, image, uuid, docker_config, env, volumes, *, stdout_callback, termination_callback):
        Waitable.__init__(self)
        Killable.__init__(self)
        Connectable.__init__(self, parent.conn(), uuid, parent, None)
        self.parent = weakref.ref(parent)
        self.location = weakref.ref(self.parent().parent())
        self.image = image
        self.processes = {}
        self.ssh_servers = {}
        self.docker_config = docker_config
        self.env = env
        self.volumes = volumes
        self.stdout_callback = stdout_callback
        self.termination_callback = termination_callback

    def start(self):
        """Start a container that was spawned with sleep=True"""
        self.conn().send_cmd(b'wake_container', {'node': self.parent().pk, 'container': self.uuid})

    def private_ip(self):
        """Reports the container's ip address"""
        self.ensure_alive()
        self.wait_until_ready()
        return self.ip

    def node(self):
        """Returns the node object this container is running on"""
        return self.parent()

    def stdin(self, data: bytes):
        """Writes the data into the container's stdin.

        :param data: The data to be written."""
        self.ensure_alive()
        self.wait_until_ready()
        self.conn().send_cmd(b'stdin_container', {'node': self.parent().pk,
                                                  'container': self.uuid},
                             bulk=data)

    def wait_tcp(self, dest_port):
        """Connects and disconnects a single connection onto this container and a given port.

        If your sevice is only capable of .accept'ing once, do not use this.

        :param dest_port: destination tcp port < 1024 is fine."""
        self.ensure_alive()
        self.wait_until_ready()
        self.location()._wait_tcp(self, dest_port)

    def attach_tunnel(self, dest_port: int, localport: Optional[int]=None, bind: Optional[str]=None) -> Tunnel:
        """Creates a TCP proxy between localhost and a container.

        :param dest_port: The TCP port on the container to connect to.
        :param localport: Optional choice of local port no - if not provided uses the dest_port.
        :param bind: Optionally bind to an address other than localhost.
        :return: A Tunnel object.

        This call does no checking to ensure the server side is ready -
        but a failed connection will not destroy the tunnel itself and will poll until connected.
        """
        self.ensure_alive()
        localport = dest_port if localport is None else localport
        return self.location()._tunnel_onto(self, dest_port, localport, bind)

    def wait_http_200(self, dest_port: Optional[int]=80, fqdn: Optional[str]='localhost', path: Optional[str]='') \
            -> Tunnel:
        """Poll until an http 200 is returned.

        :param dest_port: Override the default port.
        :param fqdn: A host name to use in the http request.
        :param path: A path on the server - appended to /
        :return: A Tunnel object.
        """
        self.ensure_alive()
        self.wait_until_ready()
        return self.location()._wait_http_200(self, dest_port, fqdn, path)

    def destroy_tunnel(self, tunnel: Tunnel):
        """Destroy a tunnel

        :param tunnel: The tunnel to be destroyed."""
        self.ensure_alive()
        self.location()._destroy_tunnel(tunnel, container=self)

    def all_tunnels(self) -> List[Tunnel]:
        """Returns all the tunnels connected to this container

        :return: A list of Tunnel objects"""
        self.ensure_alive()
        return [t for t in self.location().tunnels.values() if t.container() == self]

    def allow_connection_from(self, container: 'Container'):
        """Allow another container to call this one over private ip

        :param container: The container that will be allowed to call."""
        self.ensure_alive()
        self.wait_until_ready()
        container.wait_until_ready()
        super().allow_connection_from(container)

    def disallow_connection_from(self, container: 'Container'):
        """Stop allowing another container to call this one over private ip

        :param container: The container that will no longer be allowed to call."""
        if self.bail_if_dead():
            return
        super().disallow_connection_from(container)

    def spawn_process(self, remote_command: str,
                      data_callback: Optional[Callable]=None,
                      termination_callback: Optional[Callable]=None,
                      stderr_callback: Optional[Callable]=None) -> Process:
        """Spawn a process within a container, receives data asynchronously via a callback.

        :param remote_command: The command to remotely launch as a string (i.e. not list).
        :param data_callback: A callback for arriving data - signature (object, bytes).
        :param termination_callback: For when the process completes - signature (object), returncode.
        :param stderr_callback: For data emitted by the process's stderr stream - signature (object, bytes).
        :return: A Process object.
        """
        if isinstance(remote_command, list):
            raise ValueError("Pass the command as a single string (that gets passed to a shell), not a list")
        self.ensure_alive()
        self.wait_until_ready()

        # Cool, go.
        logging.info("Container (%s) spawning process: '%s'" % (self.uuid.decode(), remote_command))

        # get the node to launch the process for us
        # we need the uuid of the spawn command because it's used to indicate when the process has terminated
        spawn_command_uuid = shortuuid.uuid().encode()
        self.processes[spawn_command_uuid] = Process(self, spawn_command_uuid,
                                                     data_callback,
                                                     termination_callback,
                                                     stderr_callback)
        self.conn().send_cmd(b'spawn_process', {'node': self.parent().pk,
                                                'container': self.uuid,
                                                'command': remote_command},
                             uuid=spawn_command_uuid,
                             reply_callback=self._process_callback)
        logging.info("...process id: " + spawn_command_uuid.decode())
        return self.processes[spawn_command_uuid]

    def run_process(self, remote_command: str, *,
                    data_callback: Optional[Callable]=None,
                    stderr_callback: Optional[Callable]=None,
                    nolog: Optional[bool]=False) -> (bytes, bytes, str):
        """Run a process once, synchronously, without pty.

        :param remote_command: The command to run remotely.
        :param data_callback: A callback for arriving data - signature (object, bytes).
        :param stderr_callback: For data emitted by the process's stderr stream - signature (object, bytes).
        :param nolog: Don't log this command (to hide sensitive data).
        :return: stdout from the process, stderr from the process, exit code (as string).
        """
        if isinstance(remote_command, list):
            raise ValueError("Pass single shot commands a string.")
        self.ensure_alive()
        self.wait_until_ready()

        # Cool, go.
        if not nolog:
            logging.info("Container (%s) running process: '%s'" % (self.uuid.decode(), remote_command))

        # get the node to launch the process for us
        # we need the uuid of the spawn command because it's used to indicate when the process has terminated
        msg = self.conn().send_blocking_cmd(b'run_process', {'node': self.parent().pk,
                                                             'container': self.uuid,
                                                             'command': remote_command})
        if msg is None:
            raise ValueError("Blocking process failed: " + remote_command)
        if data_callback is not None and len(msg.params['stdout']) > 0:
            data_callback(self, msg.params['stdout'])
        if stderr_callback is not None and len(msg.params['stderr']) > 0:
            stderr_callback(self, msg.params['stderr'])
        return msg.params['stdout'], msg.params['stderr'], msg.params['exit_code']

    def spawn_shell(self,
                    data_callback: Optional[Callable]=None,
                    termination_callback: Optional[Callable]=None,
                    echo: bool=False) -> Process:
        """Spawn a shell within a container, expose as a process

        :param data_callback: A callback for arriving data - signature (object, bytes).
        :param termination_callback: For when the process completes - signature (object, returncode).
        :param echo: Whether or not the shell echoes input.
        :return: A Process object."""
        self.ensure_alive()
        self.wait_until_ready()

        # get the node to launch the process for us
        # we need the uuid of the spawn command because it's used to indicate when the process has terminated
        spawn_command_uuid = shortuuid.uuid().encode()
        self.processes[spawn_command_uuid] = Process(self, spawn_command_uuid, data_callback, termination_callback)
        self.conn().send_cmd(b'spawn_shell', {'node': self.parent().pk,
                                              'container': self.uuid,
                                              'echo': echo},
                             uuid=spawn_command_uuid,
                             reply_callback=self._process_callback)
        logging.info("Spawned shell: " + spawn_command_uuid.decode())
        return self.processes[spawn_command_uuid]

    def destroy_process(self, process: Process):
        """Destroy a process

        :param process: The process to be destroyed."""
        self.ensure_alive()
        if process.uuid not in self.processes:
            raise ValueError("Process is not apparently a child of this container")
        process.destroy()
        del self.processes[process.uuid]

    def all_processes(self) -> List[Process]:
        """Returns all the processes (that were manually launched) running on this container.

        :return: A list of Process objects"""
        self.ensure_alive()
        return list(self.processes.values())

    def create_ssh_server(self, port: int=2222) -> SshServer:
        """Create an ssh/sftp server on the given port.

        :param port: Local tcp port number
        :return: An SshServer object."""
        self.ensure_alive()
        self.wait_until_ready()
        s = SshServer(self, port)
        s.start()
        self.ssh_servers[s.uuid] = s
        return s

    def destroy_ssh_server(self, server):
        """Destroy an ssh/sftp server than belongs to this container.

        :param server: An SshServer object."""
        self.ensure_alive()
        if server.uuid not in self.ssh_servers:
            raise ValueError("Server does not belong to this container")
        server.stop()
        del self.ssh_servers[server.uuid]

    def fetch(self, filename: str) -> bytes:
        """Fetch a single file from the container.

        :param filename: The full-path name of the file to be retrieved.
        :return: the contents of the file as a bytes object.

        Since the file gets loaded into memory, this is a bad way to move large files (>1GB)."""
        self.ensure_alive()
        self.wait_until_ready()
        return self.conn().send_blocking_cmd(b'fetch_file', {'node': self.parent().pk,
                                                             'container': self.uuid,
                                                             'filename': filename}).bulk

    def put(self, filename: str, data: bytes):
        """Put a file into the container.

        :param filename: The full-path name of the file to be placed.
        :param data: The contents of the file as a bytes object.

        This will just overwrite so be careful. Note that new file paths are created on demand.
        Similarly to fetch, this is a bad way to move large files (>1GB).
        """
        self.ensure_alive()
        self.wait_until_ready()
        self.conn().send_blocking_cmd(b'put_file', {'node': self.parent().pk,
                                                    'container': self.uuid,
                                                    'filename': filename}, bulk=data)

    def reboot(self, reset_filesystem: Optional[bool]=False):
        """Synchronously reboot a container, optionally resetting the filesystem.

        :param reset_filesystem: Reset the container's filesystem to its 'as booted' state."""
        if self.dead:
            raise RuntimeError("Tried to restart a container but it has already been removed from the node")
        self.ensure_alive()
        self.wait_until_ready()  # in this case means it has been configured, prepared etc. once already

        # Restart
        logging.info("Restarting container: " + self.uuid.decode())
        self.mark_not_ready()  # so calls are forced to wait until the container reports it has rebooted
        self.conn().send_cmd(b'reboot_container', {'node': self.parent().pk,
                                                   'container': self.uuid,
                                                   'reset_filesystem': reset_filesystem},
                             reply_callback=self.parent()._container_status_update)
        self.wait_until_ready()

    def _internal_destroy(self, send_cmd=True):
        # Destroy this container
        if self.bail_if_dead():
            return
        self.ensure_alive()
        self.wait_until_ready()

        # Fake the processes being destroyed (they will be anyway)
        for proc in list(self.processes.values()):
            proc.destroy(with_command=False)

        # Destroy any tunnels
        for tun in list(self.all_tunnels()):
            self.location()._destroy_tunnel(tun, self, with_command=False)

        # Destroy any ssh servers
        for svr in list(self.ssh_servers.values()):
            self.destroy_ssh_server(svr)

        # Destroy (async)
        if send_cmd:
            logging.info("Destroying container: " + self.uuid.decode())
            self.conn().send_cmd(b'destroy_container', {'node': self.parent().pk,
                                                        'container': self.uuid})
        else:
            logging.info("Container has exited and/or been destroyed: " + self.uuid.decode())
        self.mark_as_dead()

        # Callback
        if self.termination_callback is not None:
            self.location().call_on_main(self.termination_callback, (self, 0))

    def _process_callback(self, msg):
        if self.bail_if_dead():
            return

        if msg.uuid not in self.processes:
            logging.debug("Message arrived for an unknown process: " + msg.uuid.decode())
            return

        logging.debug("Received data from process: " + msg.uuid.decode())
        logging.debug(msg.bulk)
        self.processes[msg.uuid].give_me_messages(msg)

    def __repr__(self):
        return "<Container `%s` image=%s ip=%s>" % (self.uuid.decode(), self.image, self.ip)


class ExternalContainer(Connectable):
    """An object representing a container managed by another session (and the same user) but advertised using a tag"""

    def __init__(self, conn, uuid, node, ip):
        super().__init__(conn, uuid, node, ip)

    def private_ip(self):
        """Reports the container's ip address"""
        return self.ip

    def __repr__(self):
        return "<ExternalContainer '%s' ip=%s>" % (self.uuid.decode(), self.ip)
