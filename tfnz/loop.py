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
import zmq
import time
import threading
import os
from .message import Message


class Loop():

    def __init__(self, skt, pk, message_type=Message):
        super().__init__()
        """Initialise (but not start) a message loop.

        skt is the zeromq socket that connects to the location.
        pk is *our* public key.
        message_type can be set to customise the Message class."""
        self.exclusive_handlers = {}
        self.fd_handlers = {}
        self.reply_callbacks = {}
        self.command_handlers = {}
        self.retry = set()
        self.skt = skt  # the main trunk socket
        self.pk = pk
        self.message_type = message_type
        self.value_error_handler = None
        self.other_error_handler = None
        self.running = False
        self.finished = False
        self.main_thread = threading.get_ident()
        self.p = zmq.Poller()
        self.p.register(self.skt, zmq.POLLIN)  # so register_reply will work even if we don't register anything else

    def register_exclusive(self, skt, handler):
        """Registers a socket and an object.handler that gets called to receive all events. Can do more than one."""
        # function signature: def callback(self, socket)
        if self.running:
            # We do this to ensure the loop isn't running, and therefore have no chance of mis-handling a packet
            raise RuntimeError("Tried to add an exclusive socket to an already running message loop")
        if skt in self.exclusive_handlers:
            raise RuntimeError("Tried to register a socket exclusively twice")
        if skt in self.command_handlers:
            raise RuntimeError("Socket is already registered with commands")
        self.exclusive_handlers[skt] = handler
        self.p.register(skt, zmq.POLLIN)
        logging.debug("Message loop has registered: " + str(skt))

    def register_commands(self, skt, obj, commands):
        """Register command callbacks directly."""
        # A single shot per socket. Pass commands as {'name': _callback, ... }
        if self.running:
            # See self.running above
            raise RuntimeError("Tried to add new commands to an already running message loop")
        if skt in self.exclusive_handlers:
            raise RuntimeError("Socket is already registered as exclusive")
        if skt in self.command_handlers:
            raise RuntimeError("Tried to register a series of commands twice for the same socket")
        self.command_handlers[skt] = (obj, commands)
        self.p.register(skt, zmq.POLLIN)
        logging.debug("Message loop has registered: " + str(skt))

    def register_reply(self, command_uuid, callback):
        """Hooking the reply to a command. Note that this will not override an exclusive socket."""
        if callback is not None:
            logging.debug("Registered a reply for uuid: " + command_uuid)
            self.reply_callbacks[command_uuid] = callback
        else:
            raise RuntimeError("Tried to register a reply for a command but passed None for the callback")

    def unregister_reply(self, command_uuid):
        """Removing the reply hook"""
        if command_uuid in self.reply_callbacks:
            logging.debug("Unregistered a reply for uuid: " + command_uuid)
            del self.reply_callbacks[command_uuid]
        else:
            logging.debug("Called unregister_reply for a uuid that isn't hooked")

    def register_fd_socket(self, socket, callback):
        """Registering a socket that's part of a proxy"""
        if callback is not None:
            logging.debug("Registered a socket fileno: " + str(socket))
            self.fd_handlers[socket] = callback
            self.p.register(socket, zmq.POLLIN)
            logging.debug("Message loop has registered: " + str(socket))
        else:
            raise RuntimeError("Tried to register an fd socket but passed None for the callback")

    def unregister_fd_socket(self, socket):
        """Unregistering proxy socket"""
        if socket in self.fd_handlers:
            logging.debug("Unregistered a socket fileno: " + str(socket))
            del self.fd_handlers[socket]
            self.p.unregister(socket)
            del socket

    def register_retry(self, obj):
        if obj not in self.retry:
            self.retry.add(obj)

    def unregister_retry(self, obj):
        if obj in self.retry:
            self.retry.remove(obj)

    def on_value_error(self, callback):
        self.value_error_handler = callback

    def on_other_error(self, callback):
        self.other_error_handler = callback

    def stop(self, wait=True):
        """Stops the message loop."""
        # the broker is single threaded so if you wait on loop finishing you're going to have a bad time, hence 'wait'
        self.running = False
        while wait and not self.finished:
            logging.debug("Waiting for loop to finish...")
            time.sleep(0.1)

    @staticmethod
    def check_basic_properties(msg, handler):
        """Helper utility to bounce missing properties before they do a bad thing"""
        necessary_params = handler[1]
        for necessary in necessary_params:
            if necessary not in msg.params:
                raise ValueError("Necessary parameter was not passed: " + necessary)
        if handler[2] and not msg.replyable():
            raise ValueError("This command needs to be replyable but the message was not: " + str(msg))

    def run(self):
        """Message loop. Runs single threaded (usually but not necessarily a background thread)."""
        # it is expected that Ctrl-C is handled elsewhere (i.e. Location.run)
        self.running = True
        tmr = None
        while self.running:

            # warning if the loop stalls
            if tmr is not None:
                latency = ((time.time()-tmr)*1000)
                if latency > 100:
                    logging.debug("Event loop stalled for (ms): " + str(latency))
            events = self.p.poll(timeout=500)
            tmr = time.time()

            # Deal with all the events
            for event in events:
                socket = event[0]

                # on an exclusive socket? (the actual process of collecting the message is owned by the callback)
                if socket in self.exclusive_handlers:
                    self.exclusive_handlers[socket](socket)
                    continue

                # an fd socket?
                if isinstance(socket, int):
                    if socket in self.fd_handlers:
                        self.fd_handlers[socket](event)
                    else:
                        logging.warning("Tunnel has gone away but an event was received for fd: " + str(socket))
                    continue

                # an ordinary message
                msg = self.message_type.receive(socket)

                # an exception?
                if 'exception' in msg.params:
                    # the exception will be thrown if it was launched from a blocking command else logged here
                    logging.error(msg.params['exception'])

                # is this a hooked reply?
                if msg.uuid in self.reply_callbacks:
                    self.reply_callbacks[msg.uuid](msg)
                    continue

                # hopefully, then, a vanilla command
                try:
                    obj, handlers = self.command_handlers[socket]  # don't replace with single
                    if msg.command in handlers:
                        handler = handlers[msg.command]
                        Loop.check_basic_properties(msg, handler)
                        handler[0](obj, msg)
                    else:
                        logging.warning("No handler was found for: " + str(msg.command))
                except ValueError as e:
                    if self.value_error_handler:
                        self.value_error_handler(e, msg, self.skt)
                    else:
                        raise e
                except BaseException as e:
                    if self.other_error_handler:
                        self.other_error_handler(e, msg, self.skt)
                    else:
                        raise e

            # any retries?
            for rt in set(self.retry):
                logging.debug("Retry: " + str(rt))
                rt()

        logging.debug("Message loop has finished")
        self.finished = True

    def __repr__(self):
        return "<tfnz.Loop object at %x (exclusive=%d commands=%d replies_callbacks=%d)>" % \
               (id(self), len(self.exclusive_handlers), len(self.command_handlers), len(self.reply_callbacks))
