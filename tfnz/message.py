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

# uuid is used to identify replies to commands including long running replies (with more than one reply)
# identifiers for everything else are to be passed explicitly in the params (as strings, because of json)

import json


class Message:

    @staticmethod
    def receive(socket):
        """Pulls one message off the socket"""
        rtn = Message()
        rtn.parts = socket.recv_multipart()
        rtn.command = rtn.parts[0].decode('ascii')
        rtn.uuid = rtn.parts[1].decode('ascii')
        rtn.params = json.loads(rtn.parts[2].decode('ascii'))
        rtn.bulk = rtn.parts[3]

        return rtn

    def replyable(self):
        """Can this message be replied to?"""
        return self.uuid is not None and self.uuid != ''

    def reply(self, socket, params=None, bulk=b''):
        """Reply to a previously received message."""
        self.parts[2] = json.dumps(params).encode('ascii') if params is not None else b'{}'
        self.parts[3] = bulk
        socket.send_multipart(self.parts)

    @staticmethod
    def send(socket, command, params=None, uuid='', bulk=b''):
        """Send a command to the location."""
        # Can be called directly but much better to use Connection.send_cmd
        parts = [command.encode('ascii'),
                 uuid.encode('ascii'),
                 json.dumps(params).encode('utf-8') if params is not None else b'{}',
                 bulk]
        socket.send_multipart(parts)

    def forward(self, socket):
        """For forwarding from the inproc connection off to the location."""
        socket.send_multipart(self.parts)

    def json(self):
        """Return a json representation, excludes bulk because that would hurt"""
        return json.dumps({'command': self.command,
                           'uuid': self.uuid,
                           'raw_params': self.raw_params})

    def __repr__(self):
        return "<tfnz.Message object at %x (command=%s uuid=%s params=%s)>" % \
               (id(self), self.command, self.uuid, self.params)
