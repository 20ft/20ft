# Copyright (c) 2018 David Preece, All rights reserved.
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

import random
import string
import logging
import time
from threading import Thread
from tfnz import Waitable
from tfnz.node import Node
from tfnz.volume import Volume
from tfnz.container import Container


class Postgresql(Waitable):
    """An object encapsulating a Postgresql server running on it's default port (5432).
        Connect with username=postgres.

        :param node: The node to spawn on.
        :param volume: A volume (object) to use as a persistent store.
        :param password: An optional password for the database, will create one if not supplied.
        :param log_callback: An optional callback for log messages -  signature (object, bytes)
        :param image: Specify a non-default image."""
    def __init__(self, node: Node, volume: Volume, *, password: str=None, log_callback=None, image=None):
        super().__init__()
        # passwords
        if password is None:
            self.password = ''.join(random.SystemRandom().choice(string.ascii_letters+string.digits) for _ in range(12))
        else:
            self.password = password

        # create
        self.ctr = node.spawn_container('postgres:alpine' if image is None else image,
                                        volumes=[(volume, '/var/lib/postgresql/data')],
                                        stdout_callback=log_callback)

        # async initialise
        self.async = Thread(target=self.wait_truly_up, name="Waiting for Postgres: " + self.ctr.uuid.decode())
        self.async.start()

    def wait_truly_up(self):
        try:
            # wait for TCP to come up
            self.ctr.wait_tcp(5432)

            # wait for the db to come up
            while True:
                rtn = self.ctr.run_process('psql -Upostgres -h%s -c "SELECT;"' % self.ctr.private_ip(), nolog=True)
                if rtn[2] == 0:
                    break
                logging.debug("Waiting for Postgresql to accept a query.")
                time.sleep(1)

            # actually set the password (passing it as part of the env doesn't work)
            self.ctr.run_process('psql -Upostgres -h%s -c "ALTER ROLE postgres WITH SUPERUSER PASSWORD \'%s\';"'
                                  % (self.ctr.private_ip(), self.password), nolog=True)  # prevent password being logged
            logging.info("Started Postgresql: " + self.ctr.uuid.decode())
            self.mark_as_ready()

        except BaseException as e:
            logging.critical(str(e))

    def ensure_database(self, name) -> bool:
        """Ensures a given database exists - returns True if it created a new one"""
        self.wait_until_ready()
        return self.ctr.run_process('psql -Upostgres -h%s -c "CREATE DATABASE %s WITH OWNER = postgres '
                                    'ENCODING = \'utf8\' LC_COLLATE = \'en_US.utf8\' LC_CTYPE = \'en_US.utf8\';"'
                                    % (self.ctr.private_ip(), name))[2] == 0

    def __getattr__(self, item):
        """Fake being inherited from the container"""
        return self.ctr.__getattribute__(item)

    def __repr__(self):
        return "<Postgresql '%s' pass=%s>" % (self.ctr.uuid.decode(), self.password)
