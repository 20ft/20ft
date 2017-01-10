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
from .container import Container, description
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
           Noboot can be used to effect pre-boot changes in the container (configurations etc), note that
           the container will not be marked as ready until it actually has booted."""
        if not no_image_check:
            self.parent().ensure_image_uploaded(image)

        # Make it go...
        descr = description(image)
        del descr[0]['ContainerConfig']
        if sleep:
            descr[0]['Config']['Entrypoint'] = None
            descr[0]['Config']['Cmd'] = ['sleep', 'inf']
        uuid = self.conn().send_cmd(b'spawn_container',
                                    {'node': str(self.pk, 'ascii'),
                                     'layer_stack': Sender.layer_stack(image),
                                     'description': descr,
                                     'env': env,
                                     'pre_boot_files': pre_boot_files}, reply_callback=self.container_status_update)

        # Create the container object
        self.containers[uuid] = Container(self, image, uuid, descr[0], env)
        logging.info("Spawning container: " + str(uuid, 'ascii'))

        return self.containers[uuid]

    def update_stats(self, stats):
        # the node telling us it's current resource state
        self.stats = stats
        logging.debug("Stats updated for node: " + self.pk)

    def container_status_update(self, msg):
        # triggered when a container goes from spawning to running
        if 'status' in msg.params and msg.params['status'] == 'running':
            logging.info("Container is running: " + str(msg.uuid, 'ascii'))
            self.containers[msg.uuid].is_ready()

    def __repr__(self):
        return "<tfnz.Node object at %x (pk=%s containers=%d)>" % (id(self), self.pk, len(self.containers))
