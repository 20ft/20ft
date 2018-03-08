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

__all__ = ['location', 'node', 'container', 'endpoint', 'volume', 'process', 'tunnel', 'docker']

import logging
import re
import weakref
import shortuuid
from messidge.client.connection import Connection
from typing import Optional, Union, List
from base64 import b64encode
from _thread import allocate_lock


class Waitable:
    """An object that can be waited on (until marked as ready)"""
    def __init__(self, locked: Optional[bool]=True):
        self.wait_lock = allocate_lock()
        if locked:
            self.wait_lock.acquire()

    def __del__(self):
        if self.wait_lock.locked():
            self.wait_lock.release()

    def wait_until_ready(self, timeout: Optional[int]=30):
        """Blocks waiting for a (normally asynchronous) update indicating the object is ready."""
        # this lock is used for waiting on while uploading layers, needs to be long
        acquired = self.wait_lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError("wait_until_ready timed out")
        self.wait_lock.release()
        return self

    def mark_as_ready(self):
        if self.wait_lock.locked():
            self.wait_lock.release()

    def mark_not_ready(self):
        if not self.wait_lock.locked():
            self.wait_lock.acquire()


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


class Connectable:
    """A resource that can be connected to in the private IP space"""
    def __init__(self, conn: Connection, uuid: str, node, ip):
        self.conn = weakref.ref(conn)
        self.uuid = uuid
        self.node_pk = node if isinstance(node, bytes) else node.pk
        self.ip = ip  # gets used externally, don't delete it

    def allow_connection_from(self, obj):
        self.conn().send_blocking_cmd(b'allow_connection', {'node': self.node_pk,
                                                            'container': self.uuid,
                                                            'ip': obj.ip})
        logging.info("Allowed connection (from %s) on: %s" % (obj.uuid.decode(), self.uuid))

    def disallow_connection_from(self, obj):
        self.conn().send_cmd(b'disallow_connection', {'node': self.node_pk,
                                                      'container': self.uuid,
                                                      'ip': obj.ip})
        logging.info("Disallowed connection (from %s) on: %s" % (obj.uuid.decode(), self.uuid))


class Taggable:
    """A resource that might have a tag - namespaced by user pk."""
    # user, uuid and tag are all *held* as bytes
    tag_re = re.compile(b'\A[^0-9a-z\-_.]*\Z')
    short_uuid_re = re.compile(b'\A[' + shortuuid.get_alphabet().encode() + b']{22}\Z')

    def __init__(self, user: Union[str, bytes], uuid: Union[str, bytes], tag: Optional[Union[str, bytes]]=None):
        if user is None or uuid is None:
            raise RuntimeError('Taggable resources must be constructed with at least a pk and uui')
        if isinstance(user, str):
            self.user = user.encode()
        else:
            self.user = user

        if isinstance(uuid, str):
            self.uuid = uuid.encode()
        else:
            self.uuid = uuid

        self.tag = None if tag is None else Taggable.valid_tag(tag)

    def uuid_key(self) -> (bytes, bytes):
        return self.user, self.uuid

    def tag_key(self) -> (bytes, bytes):
        """Effectively a namespaced tag."""
        if self.tag is None:
            return None
        return self.user, self.tag

    @staticmethod
    def valid_tag(tag: Union[bytes, str]) -> Union[bytes, None]:
        """Ensure that the passed tag is at least vaguely plausible - does not check for clashes"""
        if tag is None:
            return None
        if len(tag) == 0:
            raise ValueError("Tag passed for approval was blank")
        tag = tag.lower()
        if isinstance(tag, str):
            tag = tag.encode()
        if Taggable.tag_re.search(tag) is not None:
            raise ValueError("Tag names can only use 0-9 a-z - _ and .")
        if Taggable.short_uuid_re.match(tag) is not None:
            raise ValueError("Tag names cannot look like UUIDs")
        return tag

    def namespaced_display_name(self) -> str:
        return self.uuid.decode() if self.tag is None else (self.uuid.decode() + ':' + self.tag.decode())

    def global_display_name(self) -> str:
        return b64encode(self.user).decode() + ':' + self.namespaced_display_name()


class TaggedCollection:
    """A collection of taggable objects"""
    def __init__(self, initial: Optional[List[Taggable]]=None):
        self.objects = {}
        self.uuid_uuidkey = {}
        self.uniques = 0
        if initial is not None:
            for init in initial:
                self.add(init)

    def __del__(self):
        for obj in self.objects.values():
            del obj
        self.objects = {}

    # emulating a dictionary
    def __len__(self) -> int:
        return self.uniques

    def __getitem__(self, uuid: Union[str, bytes]) -> Taggable:  # applies to just UUID's
        if isinstance(uuid, str):
            uuidkey = self.uuid_uuidkey[uuid.encode()]
        else:
            uuidkey = self.uuid_uuidkey[uuid]
        return self.objects[uuidkey]

    def __contains__(self, uuid: Union[str, bytes]) -> bool:
        try:
            self[uuid]  # throws if it can't get it so, yes, this does actually do something
            return True
        except KeyError:
            return False

    def __setitem__(self, key, value):
        raise RuntimeError("Tagged collection can only be inserted to with the 'add' method")

    def __iter__(self):
        raise RuntimeError("Cannot iterate over a tagged collection")

    # what we came here for
    def add(self, obj: Taggable):
        if self.will_clash(obj.user, obj.uuid, obj.tag):
            raise RuntimeError("Cannot add to TaggedCollection because there will be a namespace clash")
        self.objects[obj.uuid_key()] = obj
        self.uuid_uuidkey[obj.uuid] = obj.uuid_key()
        if obj.tag_key() is not None:
            self.objects[obj.tag_key()] = obj
        self.uniques += 1

    def get(self, user: Union[bytes, str], key: Union[bytes, str]) -> Taggable:
        """Fetch using an ill-defined key: uuid or tag or uuid:tag"""
        if key is None:
            raise RuntimeError("Key not passed when fetching from TaggedCollection")
        if isinstance(user, str):
            user = user.encode()
        if isinstance(key, str):
            key = key.encode()

        # uuid or key or uuid:key?
        parts = key.split(b':')
        if len(parts) > 2:
            raise ValueError("Too many parts in tag: " + key.decode())

        # will match (user, uuid) or (user, tag)
        try:
            return self.objects[(user, parts[0])]
        except KeyError:
            # it seems as if we would need to search using parts[1] but...
            # we have both (user, uuid) and (user, tag) in the collection so it doesn't matter if we've passed
            # uuid, uuid:tag (matches UUID), or tag
            raise KeyError('Failed to get from a TaggedCollection with user=%s key=%s' % (user, key))

    def remove(self, obj: Taggable):
        del self.objects[obj.uuid_key()]
        del self.uuid_uuidkey[obj.uuid]
        if obj.tag_key() in self.objects:
            del self.objects[obj.tag_key()]
        self.uniques -= 1

    def will_clash(self, user: bytes, uuid: bytes, tag: bytes) -> bool:
        if tag is not None:
            if (user, tag) in self.objects:
                return True
        if (user, uuid) in self.objects:
            return True
        return False

    def values(self):
        return set(self.objects.values())  # de-dupe

    def __repr__(self):
        return "<TaggedCollection uniques=%d>" % self.uniques
