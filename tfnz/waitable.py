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

from _thread import allocate_lock


class Waitable:
    """Wait for an object to be ready with wait_until_ready"""
    def __init__(self):
        self.wait_lock = allocate_lock()
        self.wait_lock.acquire()

    def __del__(self):
        if self.wait_lock.locked():
            self.wait_lock.release()

    def wait_until_ready(self):
        # this lock is used for waiting on while uploading layers, needs to be long
        result = self.wait_lock.acquire(timeout=120)
        self.wait_lock.release()
        return result

    def is_ready(self):
        if self.wait_lock.locked():
            self.wait_lock.release()
