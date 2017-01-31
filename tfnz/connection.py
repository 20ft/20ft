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

import logging
import os
from threading import current_thread, main_thread
from _thread import start_new_thread, allocate_lock, get_ident
from base64 import b64decode
from DNS.lazy import dnslookup
from DNS.Base import ServerError
import zmq
import zmq.auth
import zmq.error
import shortuuid
from .message import Message
from .keys import KeyPair
from .loop import Loop
from .waitable import Waitable


class Connection(Waitable):
    """Connection onto 20ft.nz."""

    # Is expecting ~/.20ft/ to contain keys named after the location to connect to (eg)
    # -rw-r--r--  1 dpreece  staff   45B Jul  8 16:36 tiny.20ft.nz
    # -r--------  1 dpreece  staff   45B Jul  8 16:36 tiny.20ft.nz.pub

    # There are three sockets
    #   skt is the main tcp socket from here to the location and belongs to the background thread
    #   send_skt is for the main thread to use to send a command
    #   x_thread_socket is the "pickup" end of send_skt and forwards to skt
    # Note that messages received are exclusively dealt with on the background thread

    def __init__(self, location: str, root_dir: str='~/.20ft', location_ip: str=None, server_public: str=None):
        super().__init__()
        """Instantiate a connection, using the location to connect to (fqdn)"""
        # Can be used directly but you probably don't want to
        # root_dir is for expressing that the keys are not found in a hidden directory of the user's home
        # location_ip is an alternative (local) ip or name.local
        # server_public is for using an alternative public key instead of the one published on DNS (testing)
        if location_ip is not None:
            logging.info("Using local broker address: " + location_ip)
        self.connect_ip = location_ip if location_ip is not None else location
        self.location = location
        self.keys = KeyPair(location, prefix=root_dir)
        self.loop = None
        self.block_reply = allocate_lock()
        self.block_results = None

        # fetch the server's public key
        try:
            server_public_txt = dnslookup(location, 'txt') if server_public is None else [[server_public]]
        except ServerError:
            raise ValueError("No DNS record - is the location valid?: " + location)
        self.server_public = b64decode(server_public_txt[0][0])
        if len(self.server_public) != 32:
            raise RuntimeError("The DNS TXT record is broken.")

        # Should be able to connect, then.
        self.main_thread = get_ident()
        start_new_thread(self._start, ())

        # create a cross thread socket so we can send from the main thread and we forward on the background thread
        self.send_skt = zmq.Context.instance().socket(zmq.DEALER)
        self.send_skt.connect("inproc://x_thread/" + str(id(self)))

    def start(self):
        """Start message loop - separate from __init__ so we get a chance to register_exclusive/register_commands"""
        self.is_ready()

    def _start(self):
        """The message loop runs on a background thread"""
        # create the trunk socket - remember sockets must be created on the thread they are used on
        logging.info("Connecting to: %s" % self.location)
        self.skt = zmq.Context.instance().socket(zmq.DEALER)
        self.skt.reconnect_ivl = 1000  # 1/second (default is 1/10sec)
        self.skt.ipv4only = True
        self.skt.identity = self.keys.public
        self.skt.curve_secretkey = self.keys.secret_binary()
        self.skt.curve_publickey = self.keys.public_binary()
        self.skt.curve_serverkey = self.server_public
        self.skt.connect("tcp://%s:5555" % self.connect_ip)
        logging.debug("Trunk socket is: %x" % id(self.skt))

        # create the cross thread socket for forwarding
        # since there can be more than one connection in the same process we need to give it a unique id
        self.x_thread_receive = zmq.Context.instance().socket(zmq.DEALER)
        self.x_thread_receive.bind("inproc://x_thread/" + str(id(self)))
        logging.debug("Cross-thread socket is: %x" % id(self.x_thread_receive))

        # kick off a message loop
        self.loop = Loop(self.skt, self.keys.public)  # loop has to be constructed on this thread because socket
        self.loop.register_exclusive(self.x_thread_receive, self._forward)
        self.wait_until_ready()
        self.loop.run()  # blocks until loop.stop is called

    def send_cmd(self, cmd: str, params=None, bulk: bytes=b'', reply_callback=None):
        """Sends a command to the location, can route replies. Call from either thread, returns uuid.

           cmd is a binary string i.e. 'map'
           params are usually a dictionary of values but can also be a list (or None)
           bulk is for passing blobs - i.e. an entire layer
           reply_callback gives the object.method to call on the background thread when the command receives a reply
           returns uuid
        """
        # BS check
        if self.loop is None:
            raise RuntimeError("The connection has no message loop - _start has not been called.")
        if cmd is None:
            raise RuntimeError("Need to pass a command to send_cmd.")

        # send
        socket = self.send_skt if get_ident() == self.main_thread else self.skt
        if reply_callback is not None:
            # important that we register the expectation of a reply before asking the question
            uuid = shortuuid.uuid()
            self.loop.register_reply(uuid, reply_callback)
            Message.send(socket, cmd, params, uuid=uuid, bulk=bulk)
            return uuid
        else:
            # no need to create a new uuid
            Message.send(socket, cmd, params, bulk=bulk)
            return None

    def send_blocking_cmd(self, cmd: str, params=None, bulk: bytes=b'') -> Message:
        """Send a command from the main thread, block for the reply."""
        if current_thread() != main_thread():
            raise RuntimeError("You can only send blocking commands on the main thread")

        # acquire a lock, wait for the reply
        self.block_reply.acquire()  # acquires
        self.send_cmd(cmd, params, reply_callback=self._unblock, bulk=bulk)

        # when the background thread has an answer, the lock will release and we can continue
        self.block_reply.acquire()
        msg = self.block_results

        # release the lock
        self.block_reply.release()
        if 'exception' in msg.params:
            raise ValueError(msg.params['exception'])

        return msg

    def register_commands(self, obj, commands):
        """Register a list of commands to be handled by the loop."""
        while self.loop is None:
            os.sched_yield()  # loop creation has not yet had a timeslice
        self.loop.register_commands(self.skt, obj, commands)

    def location_name(self) -> str:
        """Outside access to the name/address of this location."""
        return self.location

    def pk(self) -> KeyPair:
        """Outside access to this location's public key."""
        return self.keys.public

    def _forward(self, skt):
        """Picked up from the foreground thread"""
        msg = Message.receive(skt)
        # logging.debug("Delivering from main/other thread: " + str(msg))
        msg.forward(self.skt)

    def _unblock(self, msg: Message):
        self.loop.unregister_reply(msg.uuid)
        logging.debug("Unblocking for uuid: " + msg.uuid)
        self.block_results = msg  # msg is stored first
        self.block_reply.release()

    def __repr__(self):
        return "<tfnz.Connection object at %s (location=%s)>" % (id(self), self.location)

