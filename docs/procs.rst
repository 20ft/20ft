====================
Additional Processes
====================

Docker style launch-at-boot of a single server process doesn't cover everything we might want to do with a container. The overhead of communication between two containers on the same node is very low and currently this is preferred to Kubertenes style pods.

A likely scenario is wanting to inject specialised performance monitoring, debugging or configuration updating processes. Support for long running processes with asynchronous callback is a basic architectural tenet of 20ft and hence this is more than possible. One word of caution is that injected processes are terminated as part of the restart functionality for the 20ft agent within the node itself. In very almost all cases this will not be a problem, but an elegant restart mechanism will be needed if the process is to stay live for a number of weeks or months.

Launching Processes in Containers
=================================

When launching processes there can be multiple processes running concurrently and they can be run either synchronously to completion, or asynchronously with callbacks for the stdout stream and process termination. Some examples: Synchronously... ::

    from tfnz.location import Location

    location = Location().best_node()
    container = node.spawn_container('nginx')
    container.wait_http_200()
    data = container.spawn_process('/bin/ps faxu').wait_until_complete()
    print(data.decode())

Asynchronously... ::

    import time
    from tfnz.location import Location

    def dc(obj, data):
        print(data.decode(), end='')

    def tc(obj):
        print("vmstat terminated")

    def sleep_tc(obj):
        print("---sleep terminated---")

    node = Location().best_node()
    container = node.spawn_container('nginx')
    vmstat = container.spawn_process('/sbin/vmstat 1',
                                     data_callback=dc, termination_callback=tc)
    sleep = container.spawn_process('/bin/sleep 3',
                                    termination_callback=sleep_tc)
    time.sleep(10)
    container.destroy_process(vmstat)  # just so we get the callback

Note that it's good form to express full paths when launching processes in containers to eliminate the availability (or not) of the PATH variable as a source of error.

Interacting with Processes
==========================

To interact with a long-lived process you can inject into the process's stdin stream. When running asynchronously, the callback technique above remains the same and we use ``process.stdin(b'whatever')`` to inject into the process. To run synchronously, pass ``return_reply=True`` as a parameter... ::

    from tfnz.location import Location

    location = Location()
    container = location.best_node().spawn_container('nginx')
    shell = container.spawn_process('/bin/bash')
    reply = shell.stdin("/bin/ps faxu\n".encode(), return_reply=True, drop_echo=True)
    print(reply.decode())

Launching a Shell
=================

We are able to connect to a login shell. A few caveats are that not all containers will allow you to do this; in many cases, trying to run synchronously basically doesn't work (for the initial log-on at least, data arrives in 'stutters'); and that a command is not executed until you send a 'return' ("\\n")::

    import time
    import sys
    from tfnz.location import Location


    def dc(obj, data):
        print(data.decode(), end='')
        sys.stdout.flush()


    node = Location().best_node()
    container = node.spawn_container('alpine', sleep=True).wait_until_ready()
    shell = container.spawn_shell(data_callback=dc)
    time.sleep(2)
    shell.stdin(b'ps faxu\n')
    time.sleep(1)

