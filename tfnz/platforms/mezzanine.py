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

import logging
import shortuuid
from secrets import token_urlsafe
from tfnz.location import Location
from tfnz.volume import Volume
from tfnz.components.postgresql import Postgresql
from tfnz.endpoint import WebEndpoint, Cluster


class Mezzanine:
    """Puts a Python/Django/Mezzanine instance on each node and load balances. Hosts wsgi applications.

    :param location: A location (object) to connect to.
    :param volume: A volume (object) to use as a persistent store - will be mounted on static/media/uploads
    :param sql_volume: A volume to connect to a Postgres server for SQL storage.
    :param db: An instance of a Postgresql component.
    :param fqdn: The FQDN to publish to.
    :param app_name: Name of the application (used to create file paths).
    :param image: The image to use (assumed derived 'FROM tfnz/mezzanine')
    :param log_callback: An optional callback for log messages -  signature (object, bytes)
    :param superuser: if creating from fresh set this (username, email) as the admin user
    :param debug: Whether or not to set debug on django."""

    def __init__(self, location: Location, volume: Volume, sql_volume: Volume, fqdn: str,
                 app_name: str, image, *, log_callback=None, superuser=None, debug=False):
        nodes = location.ranked_nodes()
        manage = 'python3 /%s/manage.py ' % app_name

        # spawn database (initialises async)
        self.db = Postgresql(nodes[0], sql_volume)

        # create the first webserver and use that to initialise a bunch of things
        first_server = nodes[0].spawn_container('tfnz/mezzanine' if image is None else image,
                                                volumes=[(volume, '/%s/static/media/uploads/' % app_name)])
        localsettings = Mezzanine.localsettings_template % \
                        (self.db.password, self.db.private_ip(), str(debug), token_urlsafe(32), token_urlsafe(32))
        first_server.put('/%s/%s/local_settings.py' % (app_name, app_name), localsettings.encode())
        self.db.allow_connection_from(first_server)

        # do we need to initialise?
        # ensure database is also wait_until_ready
        if self.db.ensure_database('mezzanine'):
            first_server.run_process(manage + 'createdb --noinput --nodata', data_callback=log_callback)
            if superuser is not None:
                first_server.run_process(manage + 'createsuperuser --noinput --username %s --email %s'
                                         % (superuser[0], superuser[1]), data_callback=log_callback)

        # start additional webservers
        self.webservers = [first_server]
        for node in nodes[1:]:
            server = node.spawn_container('tfnz/mezzanine' if image is None else image,
                                          volumes=[(volume, '/%s/static/media/uploads/' % app_name)])
            server.put('/%s/%s/local_settings.py' % (app_name, app_name), localsettings.encode())
            self.webservers.append(server)

        # configure and go
        for w in self.webservers:
            self.db.allow_connection_from(w)
            w.run_process('rm /etc/nginx/conf.d/default.conf')
            w.run_process('mkdir /run/nginx')
            w.put('/etc/nginx/conf.d/nginx.conf', (Mezzanine.nginx_template % (fqdn, '/%s/' % app_name)).encode())
            w.run_process(manage + 'collectstatic --noinput')
            w.spawn_process('cd %s ; gunicorn -b unix:/tmp/gunicorn.sock --workers=8 %s.wsgi'
                            % (app_name, app_name), stderr_callback=log_callback)
            w.run_process('nginx')

        # gather together and serve into an endpoint
        self.cluster = Cluster(self.webservers)
        location.endpoint_for(fqdn).publish(self.cluster, fqdn)

        # wait until we're actually able to serve
        WebEndpoint.wait_http_200(fqdn)
        logging.info("Mezzanine is up.")

    def change_password(self, username, password):
        """change the username and password of the given user - could be superuser"""
        # also, this is a bit gross
        w = self.webservers[0]
        py = Mezzanine.chpass_template % (password, shortuuid.uuid(), username, self.db.private_ip())
        w.put('update_password.py', py.encode())
        w.run_process('python3 update_password.py')
        w.run_process('rm update_password.py')

    localsettings_template = """
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "mezzanine",
        "USER": "postgres",
        "PASSWORD": "%s",
        "HOST": "%s",
        "PORT": "5432"
    }
}

ALLOWED_HOSTS = ["*"]

DEBUG = %s

SECRET_KEY = "%s"
NEVERCACHE_KEY = "%s"
"""

    nginx_template = """
upstream gunicorn {
    server unix:/tmp/gunicorn.sock fail_timeout=0;
}    

server {
    listen 80;
    server_name %s;
    charset utf-8;

    location /static/ {
        root %s;
    }

    location / {
        proxy_pass http://gunicorn;
    }
}
"""
    chpass_template = """
from django.contrib.auth.hashers import PBKDF2PasswordHasher
import psycopg2

hash = PBKDF2PasswordHasher().encode('%s', '%s')
sql = "UPDATE auth_user SET password='" + hash + "' WHERE username='%s'"

conn = psycopg2.connect("dbname=mezzanine user=postgres host=%s")
cur = conn.cursor()
cur.execute(sql)
conn.commit()
cur.close()
conn.close()
"""
