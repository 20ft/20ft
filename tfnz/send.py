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

# You might also want to 'brew install pigz' for a parallel zipper

from subprocess import check_output, call
import os.path
import hashlib
import logging
import tempfile
from .container import description


class Sender:

    def __init__(self, conn, docker_image_id):
        """Internal use: Fetch and send docker layers."""
        self.conn = conn
        self.docker_image_id = docker_image_id

        # get unique sha256's that need uploading (layer_stack throws for an invalid id)
        self.layer_stack = Sender.layer_stack(docker_image_id)
        offers = set(self.layer_stack)

        # set the list of required uploads
        self.requirements = conn.send_blocking_cmd(b'upload_requirements', list(offers)).params

    @staticmethod
    def layer_stack(docker_image_id):
        """Returns a list of the layers necessary to create the passed docker image id."""
        # find layers
        desc = description(docker_image_id)[0]  # get dictionary (throws for invalid id)
        layers = desc['RootFS']['Layers']

        # take the layers and prevent the same layer being applied twice in a row
        single_run_layers = []
        last_layer = None
        for layer in layers:
            layer = layer[7:]
            if layer == last_layer:
                continue
            single_run_layers.append(layer)
            last_layer = layer
        return single_run_layers

    def send(self):
        """Internal use: Send the missing layers to the location."""
        if len(self.requirements) == 0:
            logging.info("No layers need uploading for: " + self.docker_image_id)
            return

        # get docker to export *all* the layers (not like we have a choice, would be happy to be informed otherwise)
        logging.info("Getting docker to export layers (this can take a while)...")
        td = tempfile.TemporaryDirectory()
        fname = td.name + '/' + self.docker_image_id + '.tar'
        call(['/usr/local/bin/docker', 'save', '-o', fname, self.docker_image_id])
        os.chdir(td.name)
        call(['/usr/bin/tar', 'xf', fname])

        # sha256 and send until all our requirements are met
        dir_entries = str(check_output(['ls']), 'ascii').split('\n')
        for layer in dir_entries:
            if layer is None or layer == '' or not os.path.isdir(layer):
                continue
            layer += '/layer.tar'
            if os.path.islink(layer):  # not unique then, is it?
                continue
            with open(layer, 'rb') as file:
                logging.debug("Finding sha256: " + layer)
                data = file.read()
                sha256 = hashlib.sha256(data).hexdigest()
                if sha256 in self.requirements:
                    logging.info("Background uploading: " + layer)
                    self.conn.send_cmd(b'upload', {'sha256': sha256}, bulk=data)
