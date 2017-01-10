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
        parts = socket.recv_multipart()
        rtn.command = parts[0]
        rtn.uuid = parts[1]
        rtn.raw_params = parts[2]
        rtn.params = json.loads(str(rtn.raw_params, 'utf-8'))
        rtn.bulk = parts[3]

        # translation?
        if 'container' in rtn.params:
            rtn.params['container'] = rtn.params['container'].encode('ascii')
        if 'tunnel' in rtn.params:
            rtn.params['tunnel'] = rtn.params['tunnel'].encode('ascii')
        if 'process' in rtn.params:
            rtn.params['process'] = rtn.params['process'].encode('ascii')
        if 'uuid' in rtn.params:
            rtn.params['uuid'] = rtn.params['uuid'].encode('ascii')

        return rtn

    def replyable(self):
        """Can this message be replied to?"""
        return self.uuid is not None and self.uuid != b''

    def reply(self, socket, params=None, bulk=b''):
        """Reply to a previously received message."""
        if not self.replyable():
            logging.error("Reply called on a non-replyable message: " + str(self))
        parts = [self.command,
                 self.uuid,
                 json.dumps(params).encode('utf-8') if params is not None else b'{}',
                 bulk]
        socket.send_multipart(parts)

    @staticmethod
    def send(socket, command, params=None, uuid=b'', bulk=b''):
        """Send a command to the location."""
        # Can be called directly but much better to use Connection.send_cmd
        parts = [command,
                 uuid,
                 json.dumps(params).encode('utf-8') if params is not None else b'{}',
                 bulk]
        socket.send_multipart(parts)

    def forward(self, socket):
        """For forwarding from the inproc connection off to the location."""
        socket.send_multipart([self.command, self.uuid, self.raw_params, self.bulk])

    def json(self):
        """Return a json representation, excludes bulk because that would hurt"""
        return json.dumps({'command': str(self.command, 'ascii'),
                           'uuid': str(self.uuid, 'ascii'),
                           'raw_params': str(self.raw_params, 'utf-8')})

    @staticmethod
    def from_json(jsn):
        """Recreates the message from a json string"""
        jsn_dict = json.loads(jsn)
        rtn = Message()
        rtn.command = jsn_dict['command']
        rtn.uuid = jsn_dict['uuid']
        rtn.raw_params = jsn_dict['raw_params']
        rtn.params = json.loads(rtn.raw_params)
        rtn.bulk = b''
        return rtn

    def __repr__(self):
        return "<tfnz.Message object at %x (command=%s uuid=%s params=%s)>" % \
               (id(self), str(self.command), str(self.uuid), str(self.params))
