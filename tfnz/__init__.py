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
import shortuuid
from base64 import b64encode
from _thread import allocate_lock


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


class Taggable:
    """A resource that might have a tag - namespaced by user pk."""
    tag_re = re.compile('\A[^0-9a-z\-_.]*\Z')
    short_uuid_re = re.compile('\A[' + shortuuid.get_alphabet() + ']{22}\Z')

    def __init__(self, user: bytes, uuid: bytes, tag: str=None):
        if user is None or uuid is None:
            raise RuntimeError('Taggable resources must be constructed with at least a pk and uui')
        self.user = user
        self.uuid = uuid
        self.tag = None if tag is None else Taggable.valid_tag(tag)

    def uuid_key(self):
        return self.user, self.uuid

    def tag_key(self):
        """Effectively a namespaced tag."""
        if self.tag is None:
            return None
        return self.user, self.tag

    @staticmethod
    def valid_tag(tag):
        """Ensure that the passed tag is at least vaguely plausible - does not check for clashes"""
        if tag is None:
            return None
        if len(tag) == 0:
            raise ValueError("Tag passed for approval was blank")
        tag = tag.lower()
        if Taggable.tag_re.search(tag) is not None:
            raise ValueError("Tag names can only use 0-9 a-z - _ and .")
        if Taggable.short_uuid_re.match(tag) is not None:
            raise ValueError("Tag names cannot look like UUIDs")
        return tag

    def namespaced_display_name(self):
        return self.uuid.decode() if self.tag is None else (self.uuid.decode() + ':' + self.tag)

    def global_display_name(self):
        return b64encode(self.user).decode() + ':' + self.namespaced_display_name()


class TaggedCollection:
    """A collection of taggable objects"""
    def __init__(self, initial: []=None):
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
    def __len__(self):
        return self.uniques

    def __getitem__(self, uuid):  # applies to just UUID's
        uuidkey = self.uuid_uuidkey[uuid]
        return self.objects[uuidkey]

    def __contains__(self, uuid):
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

    def get(self, user: bytes, key):
        """Fetch using an ill-defined key: uuid or tag or uuid:tag"""
        if key is None:
            raise RuntimeError("Key not passed when fetching from TaggedCollection")

        # uuid or key or uuid:key?
        parts = key.split(':')
        if len(parts) > 2:
            raise ValueError("Too many parts in tagged object: " + key)

        # will match (user, uuid) or (user, tag)
        try:
            return self.objects[(user, parts[0])]
        except KeyError:
            # it seems as if we would need to searc using parts[1] but...
            # we have both (user, uuid) and (user, tag) in the collection so it doesn't matter if we've passed
            # uuid, uuid:tag (matches UUID), or tag
            raise KeyError("Failed to 'get' from a TaggedCollection with user=%s key=%s" % (user, key))

    def remove(self, obj: Taggable):
        del self.objects[obj.uuid_key()]
        if obj.tag_key() in self.objects:
            del self.objects[obj.tag_key()]
        self.uniques -= 1
        
    def will_clash(self, user, uuid, tag):
        if tag is not None:
            if (user, tag) in self.objects:
                return True
        if (user, uuid) in self.objects:
            return True
        return False

    def values(self):
        return set(self.objects.values())  # de-dupe
