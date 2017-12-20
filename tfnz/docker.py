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

import sys
import requests.exceptions
import json
import logging


class Docker:
    docker_socket = '/var/run/docker.sock'
    docker_url_base = 'http+unix://%2Fvar%2Frun%2Fdocker.sock'
    session = None

    @staticmethod
    def description(docker_image_id: str, conn=None) -> dict:
        """Describe a docker image.

        :param docker_image_id: Docker image id.
        :param conn: An optional connection to the location.
        :return: A dict representation of image metadata."""
        # try locally
        can_connect_local = True
        try:
            r = Docker._session().get('%s/images/%s/json' % (Docker.docker_url_base, docker_image_id))

            # local docker works but doesn't have it
            if r.status_code == 404:
                logging.info("Local docker doesn't have image, trying for remote")
            else:
                # presumably worked, cache it and return
                obj = json.loads(r.text)
                if conn is not None:
                    conn.send_cmd(b'cache_description', {'image_id': docker_image_id, 'description': obj})
                return obj
        except requests.exceptions.ConnectionError:
            can_connect_local = False

        # no go locally, try remotely
        have_description = False
        if conn is not None:
            logging.info("Retrieving description: " + docker_image_id)
            msg = conn.send_blocking_cmd(b'retrieve_description', {'image_id': docker_image_id})
            if 'description' in msg.params:
                return msg.params['description']

        # image is in neither location
        if can_connect_local:
            raise RuntimeError("Cannot find image in either local docker or remote image cache: " + docker_image_id)
        else:
            # local's dead, too
            Docker._docker_warning()

    @staticmethod
    def tarball(docker_image_id: str) -> bytes:
        """Retrieve the tarball of a docker image.

        :param docker_image_id: Docker image id.
        :return: A stream of bytes that would be the contents of the tar archive."""
        try:
            r = Docker._session().get('%s/images/%s/get' % (Docker.docker_url_base, docker_image_id))
            return r.content
        except requests.exceptions.ConnectionError:
            Docker._docker_warning()


    @staticmethod
    def last_image() -> str:
        """Finding the most recent docker image on this machine.

        :return: Docker image id of the most recently built docker image"""
        r = None
        try:
            r = Docker._session().get('%s/images/json' % Docker.docker_url_base)
        except requests.exceptions.ConnectionError:
            Docker._docker_warning()
        if len(r.text) == 0:
            raise ValueError("Docker has no local images.")
        obj = json.loads(r.text)
        return obj[0]['Id'][7:19]

    @staticmethod
    def _docker_warning():
        print("""
    Cannot (and need to) connect to the docker socket.
    
    --------------------------------------
    Is docker running? You may need to run
    sudo chmod 666 /var/run/docker.sock
    --------------------------------------
    """, file=sys.stderr)
        raise RuntimeError("Need a functioning local Docker")

    @staticmethod
    def _session():
        # when we need unix sockets (not deployed on server, hence late binding)
        if Docker.session is None:
            import requests_unixsocket
            Docker.session = requests_unixsocket.Session()
        return Docker.session
