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

from subprocess import Popen, PIPE
import hashlib
import logging
import io
from tarfile import TarFile
from . import description


class Sender:

    def __init__(self, conn, docker_image_id):
        """Internal use: Fetch and send docker layers."""
        self.conn = conn
        self.docker_image_id = docker_image_id

        # get unique sha256's that need uploading (layer_stack throws for an invalid id)
        offers = set(Sender.layer_stack(docker_image_id))

        # set the list of required uploads
        self.requirements = conn.send_blocking_cmd('upload_requirements', list(offers)).params
        self.req_to_go = len(self.requirements)

    @staticmethod
    def layer_stack(docker_image_id):
        """Returns a list of the layers necessary to create the passed docker image id."""
        # find layers
        desc = description(docker_image_id)  # get dictionary (throws for invalid id)
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
        # note that making a fake registry was tried and found to be horrible
        logging.info("Getting docker to export layers...")
        process = Popen(['/usr/local/bin/docker', 'save', self.docker_image_id], stdout=PIPE)
        (docker_stdout, docker_stderr) = process.communicate()
        raw_top_tar = io.BytesIO(docker_stdout)
        top_tar = TarFile(fileobj=raw_top_tar)

        # sha256 and send until all our requirements are met
        for member in top_tar.getmembers():
            # only even remotely interested in the layers
            if '/layer.tar' not in str(member):
                continue

            # extract and hash the data
            layer_data = top_tar.extractfile(member).read()
            sha256 = hashlib.sha256(layer_data).hexdigest()

            # is this one we care about?
            if sha256 in self.requirements:
                logging.info("Background uploading: " + sha256)
                self.conn.send_cmd('upload', {'sha256': sha256}, bulk=layer_data)
                self.req_to_go -= 1
                if self.req_to_go == 0:  # done
                    break
