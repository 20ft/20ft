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
import weakref
from . import description
from .container import Container
from .send import Sender


class Node:
    """An object representing a single node. Do not construct directly, use ranked_nodes or best_node on the location.
    """
    def __init__(self, parent, pk, conn, stats):
        # Internal Use: Don't construct nodes directly
        self.parent = weakref.ref(parent)
        self.pk = pk
        self.conn = weakref.ref(conn)
        self.stats = stats
        self.containers = {}

    def spawn(self, image, env=None, sleep=False, pre_boot_files={}, no_image_check=False) -> Container:
        """Asynchronously spawns a container on the node.

           :param image: the short image id from Docker.
           :param env: a list of environment name, value pairs to be passed.
           :param sleep: replaces the Entrypoint/Cmd with a single blocking command (container still boots).
           :param pre_boot_files: A dictionary of file name and contents to be written in the container before booting.
           :param no_image_check: does not check to ensure image has been uploaded.
           :return: A Container object.

           The resulting Container is initially a placeholder until the container has spawned.
           To block until it has actually spawned call wait_until_ready() on the container.
           Any layers that need to be uploaded to the location are uploaded automatically.
           Note that the container will not be marked as ready until it actually has booted."""
        if not no_image_check:
            self.parent().ensure_image_uploaded(image)

        # Make it go...
        descr = description(image)
        if 'ContainerConfig' in descr:
            del descr['ContainerConfig']
        if sleep:
            descr['Config']['Entrypoint'] = None
            descr['Config']['Cmd'] = ['sleep', 'inf']
        uuid = self.conn().send_cmd('spawn_container',
                                    {'node': self.pk,
                                     'layer_stack': Sender.layer_stack(image),
                                     'description': descr,
                                     'env': env,
                                     'pre_boot_files': pre_boot_files}, reply_callback=self.container_status_update)

        # Create the container object
        self.containers[uuid] = Container(self, image, uuid, descr, env)
        logging.info("Spawning container: " + uuid)

        return self.containers[uuid]

    def destroy_container(self, container: Container):
        """Destroy a container running on this node. Will also destroy any tunnels onto the container.

        :param container: The container to be destroyed."""
        container.ensure_alive()
        loc = self.parent()
        for tun in list(loc.tunnels.values()):
            if tun.container is container:
                loc.destroy_tunnel(tun)
        self.containers[container.uuid].internal_destroy()
        del self.containers[container.uuid]

    def all_containers(self) -> [Container]:
        """Returns all the containers running on this node (for *this* session)"""
        return list(self.containers.values())

    def update_stats(self, stats):
        # the node telling us it's current resource state
        self.stats = stats
        logging.debug("Stats updated for node: " + self.pk)

    def container_status_update(self, msg):
        try:
            container = self.containers[msg.uuid]
            if container.bail_if_dead():
                return
        except KeyError:
            logging.warning("Status update was sent for a non-existent container")

        if 'exception' in msg.params:
            raise ValueError(msg.params['exception'])

        if msg.params['status'] == 'running':
            logging.info("Container is running: " + msg.uuid)
            container._ip = msg.params['ip']
            container.mark_as_ready()

    def __repr__(self):
        return "<tfnz.node.Node object at %x (pk=%s containers=%d)>" % (id(self), self.pk, len(self.containers))
