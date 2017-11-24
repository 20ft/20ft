====================
Developing with 20ft
====================

This section is about developing *with* 20ft - i.e. purely as a container substrate. For development of 20ft applications, see the sections on using the SDK. These docs are also 'light' while integration bugs with third party IDE's are worked through.

In essence the day-to-day workflow with 20ft aims to be very much like developing for a remote vm, `using the ssh and sftp tools <cli.html#ssh-sftp>`_. Unfortunately it is not currently possible to create a reverse proxy (i.e. 'out' of a container) so 'call back' style debuggers are not an option.

Automated Tests
===============

