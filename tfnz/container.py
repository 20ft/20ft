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
from subprocess import PIPE, Popen, TimeoutExpired
from .waitable import Waitable
from .process import Process


class Container(Waitable):
    """An object representing a single container. Do not instantiate directly, use node.spawn."""
    def __init__(self, parent, image: str, uuid: bytes, docker_config: dict=None, env: dict=None):
        super().__init__()
        self.parent = weakref.ref(parent)
        self.conn = weakref.ref(self.parent().conn())
        self.image = image
        self.uuid = uuid
        self.processes = {}
        self.docker_config = docker_config
        self.env = env
        self.ip = None

    def destroy(self):
        """Destroy this container."""
        self.wait_until_ready()
        self.conn().send_cmd(b'destroy_container',
                             {'node': str(self.parent().pk, 'ascii'),
                              'container': str(self.uuid, 'ascii')})
        loc = self.parent().parent()
        for tun in list(loc.tunnels.values()):
            if tun.container is self:
                loc.destroy_tunnel(tun)
        logging.info("Destroyed container: " + str(self.uuid, 'ascii'))

    def spawn_process(self, remote_command, data_callback=None, termination_callback=None) -> Process:
        """Spawn a process within a container, receives data asynchronously via a callback.

        :param remote_command: The process to remotely launch.
        :param data_callback: A callback for arriving data - signature (object, bytes)
        :param termination_callback: For when the process completes - signature (object)
        :return: A Process object.

        Note that the remote command can be either the string ("ps faxu") format or list (["ps", "faxu"]) format."""
        self.wait_until_ready()

        # Cool, go.
        if isinstance(remote_command, str):
            remote_command = [remote_command]
        logging.info("Container (%s) spawning process: %s" % (str(self.uuid, 'ascii'), json.dumps(remote_command)))

        # get the node to launch the process for us
        # we need the uuid of the spawn command because it's used to indicate when the process has terminated
        spawn_command_uuid = self.conn().send_cmd(b'spawn_process',
                             {'node': str(self.parent().pk, 'ascii'),
                              'container': str(self.uuid, 'ascii'),
                              'command': remote_command}, reply_callback=self._process_callback)
        rtn = Process(self, spawn_command_uuid, data_callback, termination_callback)
        self.processes[spawn_command_uuid] = rtn
        return rtn

    def fetch(self, filename: str) -> bytes:
        """Fetch a single file from the container, may throw a ValueException.

        :param: filename: The full-path name of the file to be retrieved.
        :return: the contents of the file as a bytes object.

        Since the file gets loaded into memory, this is probably not the best way to move large files."""
        self.wait_until_ready()
        return self.conn().send_blocking_cmd(b'fetch',
                                             {'node': str(self.parent().pk, 'ascii'),
                                              'container': str(self.uuid, 'ascii'),
                                              'filename': filename}).bulk

    def put(self, filename: str, data: bytes):
        """Put a file into the container, may throw a ValueException.

        :param: filename: The full-path name of the file to be placed.
        :param: data: The contents of the file as a bytes object.

        This will just overwrite so be careful. Note that new file paths are created on demand.
        """
        self.wait_until_ready()
        self.conn().send_blocking_cmd(b'put',
                                      {'node': str(self.parent().pk, 'ascii'),
                                       'container': str(self.uuid, 'ascii'),
                                       'filename': filename}, bulk=data)

    def logs(self) -> [dict]:
        """Fetches the stdout log from the container.

        :return: A list of dictionary objects.

        The dictionary keys are: 'log' - a single log item; 'stream' - the stream it was received on;
        and 'time' - the server timestamp when the message was logged."""
        self.wait_until_ready()
        raw = self.conn().send_blocking_cmd(b'fetch_log',
                                           {'node': str(self.parent().pk, 'ascii'),
                                            'container': str(self.uuid, 'ascii')}).bulk
        lines = str(raw, 'utf-8').split('\n')
        return [json.loads(line) for line in lines if line != '']

    def _process_callback(self, msg):
        # we have to use message id to identify the container because it's needed to create a long running conversation
        # obituary?
        if msg.command == b'' and msg.params == {} and msg.bulk == b'no_more_replies':
            logging.info("Process terminated: " + str(msg.uuid, 'ascii'))
            del self.processes[msg.uuid]
            return

        # normal arrival of data
        if msg.uuid not in self.processes:
            logging.debug("Message arrived for an unknown process: " + str(msg.uuid, 'ascii'))
            return
        logging.debug("Received data from process (%s): \n%s" %
                      (str(msg.uuid, 'ascii'), str(msg.bulk, 'utf-8')))
        self.processes[msg.uuid].give_me_messages(msg)

    def __repr__(self):
        return "<tfnz.Container object at %x (image=%s uuid=%s)>" % (id(self), self.image, str(self.uuid, 'ascii'))


def description(docker_image_id) -> dict:
    # Get metadata from local Docker.
    inspect_obj = Popen(["/usr/local/bin/docker", "inspect", docker_image_id], stdout=PIPE, stderr=PIPE)
    try:
        out = inspect_obj.communicate(timeout=5)
    except TimeoutExpired:
        raise RuntimeError("The docker daemon is not responding to an 'inspect' command.")
    if out[1] != b'':
        raise RuntimeError("Docker cannot find image: " + docker_image_id)
    return json.loads(str(out[0], 'ascii'))
