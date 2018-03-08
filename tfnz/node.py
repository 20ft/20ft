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
import weakref
import shortuuid
from base64 import b64encode
from typing import List, Optional, Tuple
from messidge.client.message import Message
from .docker import Docker
from .container import Container
from .volume import Volume


class Node:
    """An object representing a single node. Do not construct directly, use ranked_nodes on the location."""
    def __init__(self, parent, pk, conn, stats):
        # Internal Use: Don't construct nodes directly
        self.parent = weakref.ref(parent)
        self.pk = pk
        self.conn = weakref.ref(conn)
        self.stats = stats  #: A dictionary of performance stats for this node. Automatically kept up to date.
        self.containers = {}  #: A uuid->object map of containers running on this node (for the current session).

    def spawn_container(self, image: str, *,
                        env: Optional[List[Tuple[str, str]]]=None,
                        sleep: Optional[bool]=False,
                        volumes: Optional[List[Tuple[Volume, str]]]=None,
                        pre_boot_files: Optional[List[Tuple[str, bytes]]]=None,
                        command: Optional[str]=None,
                        stdout_callback: Optional[object]=None,
                        termination_callback: Optional[object]=None,
                        advertised_tag: Optional[str]=None) -> Container:
        """Asynchronously (by default) spawns a container on the node.

        :param image: the short image id from Docker.
        :param env: a list of environment name, value pairs to be passed.
        :param sleep: replaces the Entrypoint/Cmd with a single blocking command (container still boots).
        :param volumes: a list of (volume, mountpoint) pairs.
        :param pre_boot_files: List (filename, data) pairs to write into the container before booting.
        :param command: ignores Entrypoint/Cmd and launches with this script instead, list not string.
        :param stdout_callback: Called when the container sends output - signature (container, string).
        :param termination_callback: For when the container completes - signature (container, returncode).
        :param advertised_tag: A tag used so other sessions (for the same user) can reference the container.
        :return: A Container object.

        The resulting Container is initially a placeholder until the container has spawned.
        Any layers that need to be uploaded to the location are uploaded automatically.
        Note that the container will not be marked as ready until it actually has booted.

        To launch synchronously call wait_until_ready() on the container. This will also cause any exceptions
        to be transported to the calling thread."""

        # Ensure the lists are lists of tuples (or None)
        if env is not None and len(env) > 0:
            try:
                if len(env[0]) != 2:
                    raise TypeError  # do this because env[0] throws the same if we pass the wrong type
            except TypeError:
                raise ValueError("You need to pass a list of tuples for env vars - [(variable_name, data), ...]")
        if volumes is not None and len(volumes) > 0:
            try:
                for vol in volumes:
                    if len(vol) != 2:
                        raise TypeError
            except TypeError:
                raise ValueError("You need to pass a list of tuples for volumes - [(volume_object, mount_point), ...]")
        if pre_boot_files is not None and len(pre_boot_files) > 0:
            try:
                if len(pre_boot_files[0]) != 2:
                    raise TypeError
            except TypeError:
                raise ValueError("You need to pass a list of tuples for pre-boot files - [(filename, data), ...]")
        if advertised_tag is not None:
            # will throw an exception if it's no good
            reply = self.conn().send_blocking_cmd(b'approve_tag', {'user': self.parent().user_pk,
                                                                   'tag': advertised_tag})

        # Make it go...
        descr = Docker.description(image, self.conn())

        if command is not None:
            descr['Config']['Entrypoint'] = []
            descr['Config']['Cmd'] = command  # will overwrite the container's config
        vol_struct = [(vol[0].uuid, vol[1]) for vol in volumes] if volumes is not None else None
        layers = self.parent().ensure_image_uploaded(image, descr=descr)

        # Create the container object then tell the node to actually create it
        uuid = shortuuid.uuid().encode()
        self.containers[uuid] = Container(self, image, uuid, descr, env, volumes,
                                          stdout_callback=stdout_callback, termination_callback=termination_callback)
        logging.info("Spawning container: " + uuid.decode())
        cookie = {'session': self.conn().rid, 'user': self.parent().user_pk, 'tag': advertised_tag}
        self.conn().send_cmd(b'spawn_container', {'node': self.pk,
                                                  'layer_stack': layers,
                                                  'description': descr,
                                                  'env': env,
                                                  'volumes': vol_struct,
                                                  'pre_boot_files': pre_boot_files,
                                                  'sleep': sleep,
                                                  'cookie': cookie},
                             uuid=uuid,
                             reply_callback=self._container_status_update)
        return self.containers[uuid]

    def destroy_container(self, container: Container):
        """Destroy a container running on this node. Will also destroy any tunnels onto the container.

        :param container: The container to be destroyed."""
        container.ensure_alive()
        container._internal_destroy()
        # removing from .containers and marking any volumes as being free happens in container_status_update

    def all_containers(self) -> List[Container]:
        """Returns a list of all the containers running on this node (for *this* session)

        :return: A list of Container objects."""
        return list(self.containers.values())

    def _internal_destroy(self):
        """Called when the node needs to clean itself up"""
        # fake container status update messages
        for ctr in self.containers.values():
            msg = Message()
            msg.uuid = ctr.uuid
            msg.params = {'status': 'destroyed'}
            self._container_status_update(msg)

    def _update_stats(self, stats):
        # the node telling us it's current resource state
        self.stats = stats

    def _container_status_update(self, msg):
        try:
            container = self.containers[msg.uuid]
        except KeyError:
            logging.debug("Status update was sent for a non-existent container")
            return

        if 'exception' in msg.params:
            self.parent().raise_on_main(ValueError(msg.params['exception']))
            container.mark_as_ready()
            return

        if 'status' not in msg.params:
            if container.stdout_callback is not None:
                container.stdout_callback(container, msg.bulk)
            return

        if msg.params['status'] == 'running':
            logging.info("Container is running: " + msg.uuid.decode())
            logging.info("...startup time was: %.3fs" % msg.params['startup_time'])
            container.ip = msg.params['ip']
            container.mark_as_ready()
            return

        if msg.params['status'] == 'destroyed':
            # wait lock will still be locked if the container did not successfully start
            if container.wait_lock.locked():
                self.parent().raise_on_main(ValueError("Container did not manage to start"))
                container.mark_as_ready()  # to unblock the lock if nothing else

            # destroy
            container._internal_destroy(send_cmd=False)
            del self.containers[msg.uuid]

    def __repr__(self):
        return "<Node '%s' containers=%d>" % \
               (b64encode(self.pk).decode(), len(self.containers))
