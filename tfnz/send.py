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

import hashlib
import logging
import io
import lzma
from tarfile import TarFile, ReadError
from .docker import Docker


class Sender:

    @staticmethod
    def layer_stack(descr):
        """Returns a list of the layers necessary to create the passed docker image id."""
        # find layers
        layers = descr['RootFS']['Layers']

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

    @staticmethod
    def upload_requirements(layers, conn):
        # ask the location what it needs
        return conn.send_blocking_cmd(b'upload_requirements', {'layers': layers}).params

    @staticmethod
    def send(docker_image_id, layers, conn):
        """Internal use: Send the missing layers to the location."""
        if len(layers) == 0:
            logging.info("No layers need uploading for: " + docker_image_id)
            return

        # get docker to export *all* the layers (not like we have a choice, would be happy to be informed otherwise)
        # note that making a fake registry was tried and found to be horrible
        logging.info("Waiting for Docker to export image...")
        tarball = Docker.tarball(docker_image_id)
        try:
            raw_top_tar = io.BytesIO(tarball)
            top_tar = TarFile(fileobj=raw_top_tar)
        except ReadError:
            raise RuntimeError("Local docker does not appear to have image: " + docker_image_id)

        # sha256 and send until all our requirements are met
        for member in top_tar.getmembers():
            # only even remotely interested in the layers
            logging.debug("Examining: " + str(member))
            if '/layer.tar' not in str(member):
                continue

            # extract and hash the data
            layer_data = top_tar.extractfile(member).read()
            sha256 = hashlib.sha256(layer_data).hexdigest()

            # is this one we care about?
            if sha256 in layers:
                logging.info("Uploading: " + sha256[:16])

                # send in compressed 4MB chunks
                slab_size = 4*1024*1024
                data_loc = 0
                slab = 0
                data_length = len(layer_data)
                logging.info("Uploading slabs: " + str((data_length // slab_size) + 1))
                while data_loc < data_length:
                    end_byte = (slab+1) * slab_size
                    if end_byte >= len(layer_data):
                        end_byte = len(layer_data)
                    send_data = lzma.compress(layer_data[data_loc:end_byte], preset=1)
                    reply = conn.send_blocking_cmd(b'upload_slab', {'sha256': sha256, 'slab': slab}, bulk=send_data)
                    logging.info(reply.params['log'])
                    data_loc += slab_size
                    slab += 1

                # this is the end
                # the upload_complete call can take ages to happen because it'll be behind all the slabs
                msg = conn.send_blocking_cmd(b'upload_complete', {'sha256': sha256, 'slabs': slab}, timeout=300)
                logging.info(msg.params['log'])

