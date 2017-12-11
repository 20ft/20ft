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
import re
import weakref
from _thread import allocate_lock
from threading import Thread
from bottle import run, Bottle
from sys import exit
from base64 import b64encode


class Waitable:
    """An object that can be waited on (until marked as ready)"""
    def __init__(self, locked=True):
        self.wait_lock = allocate_lock()
        self.exception = None
        if locked:
            self.wait_lock.acquire()

    def __del__(self):
        if self.wait_lock.locked():
            self.wait_lock.release()

    def wait_until_ready(self, timeout=30):
        """Blocks waiting for a (normally asynchronous) update indicating the object is ready.

        Note this also causes exceptions that would previously have been raised on the background thread
        to be raise on the calling (i.e. main) thread."""
        # this lock is used for waiting on while uploading layers, needs to be long
        self.wait_lock.acquire(timeout=timeout)
        self.wait_lock.release()
        if self.exception:
            raise self.exception
        return self

    def mark_as_ready(self):
        if self.wait_lock.locked():
            self.wait_lock.release()

    def mark_not_ready(self):
        if not self.wait_lock.locked():
            self.wait_lock.acquire()

    def unblock_and_raise(self, exception):
        # releases the lock but causes the thread in 'wait_until_ready' to raise an exception
        self.exception = exception
        self.mark_as_ready()


class Killable:
    """An object that can be marked as dead - and either bail and carry on, or raise if dead"""
    def __init__(self):
        self.dead = False

    def mark_as_dead(self):
        self.dead = True

    def bail_if_dead(self):
        # use this where the user is not really to blame
        if self.dead:
            logging.debug("Object was previously terminated (carrying on): " + self.__repr__())
        return self.dead

    def ensure_alive(self):
        # use this where the user has tried to use the object but it's kinda their fault it's no longer there
        if self.dead:
            raise ValueError("Cannot call method on a terminated object: " + self.__repr__())


class Taggable:
    """A resource that has a tag"""
    tag_re = re.compile('[^0-9a-z\-_.]')

    def __init__(self, uuid, tag=None, user=None):
        self.uuid = uuid
        self.tag = tag
        self.user = user

    @staticmethod
    def ok_tag(tag):
        if tag is None:
            return None
        tag = tag.lower()
        if Taggable.tag_re.search(tag) is not None:
            raise ValueError("Tag names can only use 0-9 a-z - _ and .")
        return tag

    def display_name(self):
        return self.uuid.decode() if self.tag is None else (self.uuid.decode() + ':' + self.tag)

    def user_tag(self):
        return Taggable.create_user_tag(self.user, self.tag)

    @staticmethod
    def create_user_tag(user, tag):
        if tag is None:
            return None
        return b64encode(user).decode() + tag if user is not None else tag


class Connectable:
    """A resource that can be connected to in the private IP space"""
    def __init__(self, conn, uuid, node, ip):
        self.conn = weakref.ref(conn)
        self.uuid = uuid
        self.node_pk = node if isinstance(node, bytes) else node.pk
        self.ip = ip

    def allow_connection_from(self, obj):
        self.conn().send_blocking_cmd(b'allow_connection', {'node': self.node_pk,
                                                            'container': self.uuid,
                                                            'ip': obj.ip})
        logging.info("Allowed connection (from %s) on: %s" % (str(obj.uuid), str(self.uuid)))

    def disallow_connection_from(self, obj):
        self.conn().send_cmd(b'disallow_connection', {'node': self.node_pk,
                                                      'container': self.uuid,
                                                      'ip': obj.ip})
        logging.info("Disallowed connection (from %s) on: %s" % (str(obj.uuid), str(self.uuid)))


class TaggedCollection:
    """A collection of tagged objects - plus tag management code"""
    def __init__(self, objects: list=None):
        """pass a uuid->object map of Taggable objects"""
        self.objects = {}
        if objects is None:
            return
        for obj in objects:
            self.add(obj)

    def __contains__(self, uuid):
        return uuid in self.objects

    def __getitem__(self, item):
        return self.objects[item]

    def get(self, key, user=None):
        """Fetches using a tag, uuid or display name to an object"""
        if isinstance(key, bytes):
            key = key.decode()  # passing a pure uuid will arrive as bytes
        if ':' in key:
            uuid, key = key.split(':')
        else:
            uuid = key
        uuid = uuid.encode()  # uuid's are always stored as binary
        try:  # try just the uuid
            return self.objects[uuid]
        except KeyError:
            # try just the tag
            ut = Taggable.create_user_tag(user, key)
            return self.objects[ut]

    def __len__(self):
        return len(self.values())

    def add(self, obj: Taggable):
        self.raise_for_clash(obj)
        self.objects[obj.uuid] = obj
        if obj.tag is not None:
            self.objects[obj.user_tag()] = obj

    def remove(self, obj: Taggable):
        del self.objects[obj.uuid]
        if obj.user_tag() in self.objects:
            del self.objects[obj.user_tag()]

    def clear(self):
        self.objects.clear()
        
    def will_clash(self, obj):
        ut = obj.user_tag()
        return ut in self.objects

    def raise_for_clash(self, obj):
        if self.will_clash(obj):
            raise ValueError("Tag is already being used")

    def raise_if_will_clash(self, user, tag):
        if tag is None:
            return
        ut = Taggable.create_user_tag(user, tag)
        if ut in self.objects:
            raise ValueError("Tag is already being used")

    def keys(self):
        return self.objects.keys()

    def values(self):
        return set(self.objects.values())  # de-dupe

    def items(self):
        return self.objects.items()


inspection_server = Bottle()


class InspectionServer(Thread):
    """A thread for running an inspection server."""
    parent = None  # done as a class variable because the route method needs to be static
    port = None

    def __init__(self, parent, port):
        super().__init__(target=self.serve, name=str("Inspection server"), daemon=True)
        InspectionServer.parent = weakref.ref(parent)
        InspectionServer.port = port
        self.start()

    @staticmethod
    def serve():
        try:
            logging.info("Started inspection server: 127.0.0.1:" + str(InspectionServer.port))
            run(app=inspection_server, host='127.0.0.1', port=InspectionServer.port, quiet=True)
        except OSError:
            logging.critical("Could not bind inspection server, exiting")
            exit(1)

    @staticmethod
    def stop():
        inspection_server.close()

    def __repr__(self):
        return "<tfnz.InspectionServer object at %x>" % id(self)
