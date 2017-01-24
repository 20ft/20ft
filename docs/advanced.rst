=================
Advanced Spawning
=================

Pre-boot files
==============

In reality it's rare that a single configuration, baked into the container image during ``docker build``, is going to be suitable for all situations. A database server will need different user configuration; a load balancer needs to be told *what* to load balance; a container under test needs to be passed fixtures and so on. The 'traditional' Docker way of doing this is to write a script that gets started in lieu of the desired process start, is passed various parameters in environment variables and is expected to render any configuration changes within the container itself before starting the desired process. They're nasty to write; worse to debug; and quickly become informal (ie undocumented) interfaces onto the underlying functionality.

Thankfully there's a better way to effect a dynamic configuration and that's by using pre-boot files. These are just text files that are passed as part of the ``spawn`` call and are written into the container immediately prior to boot. They are nothing more than renders of the application's configuration files - and as such can be created with anything that will render a template. Here is a simple implementation...::

    import signal
    from tfnz.location import Location

    location = Location(debug_log=True)
    preboot = {'/usr/share/nginx/html/index.html': 'Hello World!'}
    container = location.best_node().spawn('nginx', pre_boot_files=preboot)
    container.attach_browser()
    signal.pause()

Obviously you are free to debug these renders client side, and in Python (instead of bash). Preboot files also make an excellent basis for higher level components i.e. a single 'LoadBalancer' class that uses pre-boot files as it's implementation.

Launching Processes in Containers
=================================

"Container style" launch-at-boot of a single server process obviously doesn't cover all use cases so in 20ft it's possible to launch a process inside a pre-booted container. There can be multiple processes running concurrently and they can be run either synchronously to completion, or asynchronously with callbacks for the stdout stream and process termination. Some examples: Synchronously... ::

    from tfnz.location import Location

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    container.wait_http_200()
    data = container.spawn_process('ps faxu').wait_until_complete()
    print(str(data, 'ascii'))

Asynchronously... ::

    import time
    from tfnz.location import Location

    def dc(obj, data):
        print(str(data, 'ascii'), end='')

    def tc(obj):
        print("Vmstat terminated")

    def sleep_tc(obj):
        print("---Sleep terminated---")

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    vmstat = container.spawn_process('vmstat 1', data_callback=dc, termination_callback=tc)
    sleep = container.spawn_process('sleep 3', termination_callback=sleep_tc)
    time.sleep(10)
    vmstat.destroy()  # just so we get the termination callback - would still garbage collect without it

The concept of multiple processes in a single container can be implemented by starting the container 'asleep' then launching processes as and when you see fit. This is illustrated below... ::

    import signal
    from tfnz.location import Location

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx', sleep=True)
    print(str(container.spawn_process('ps').wait_until_complete(), 'ascii'))
    process = container.spawn_process('nginx')
    container.wait_http_200()
    print(str(container.spawn_process('ps').wait_until_complete(), 'ascii'))
    signal.pause()

Concurrent Booting
==================

20ft containers are started asynchronously - that is to say that the actions of asking a container to start and the container having started are, from the perspective of the user, completely decoupled. As with all things this is obvious given an example:

The image used in these examples is a fairly heavy Apache/Mezzanine/Django/Postgres stack with non-trivial startup costs. Consider the synchronous case::

    import logging
    from tfnz.location import Location

    location = Location('tiny.20ft.nz', debug_log=False)
    location.ensure_image_uploaded('337c501c333c')
    logging.info("-----Starting")
    for n in range(0, 10):
        container = location.best_node().spawn('337c501c333c', no_image_check=True)
        container.wait_http_200(fqdn="www.atomicdroplet.com")
    logging.info("-----Finished")

Results in::

    1207165016.497 INFO     Connecting to: tiny.20ft.nz
    1207165016.609 INFO     Location has sent resource offer
    1207165016.610 INFO     Ensuring layers are uploaded for: 337c501c333c
    1207165016.684 INFO     No layers need uploading for: 337c501c333c
    1207165016.684 INFO     -----Starting
    1207165016.763 INFO     Spawning container: jcSGEaxhkKxQwwHomowbdb
    1207165016.763 INFO     Waiting on http 200: jcSGEaxhkKxQwwHomowbdb
    .....snip
    1207165125.548 INFO     Container is running: uvUiGjDMZJ3yanGFoCHJVb
    1207165125.549 INFO     Created tunnel object onto: uvUiGjDMZJ3yanGFoCHJVb (3365 -> 80)
    1207165132.579 INFO     Connected onto: http://www.atomicdroplet.com:3365/
    1207165132.579 INFO     -----Finished

76.9 seconds. In parallel::

    import logging
    from tfnz.location import Location

    location = Location('tiny.20ft.nz', debug_log=False)
    location.ensure_image_uploaded('337c501c333c')
    containers = []
    logging.info("-----Starting")
    for n in range(0, 10):
        container = location.best_node().spawn('337c501c333c', no_image_check=True)
        containers.append(container)
    for container in containers:
        container.wait_http_200(fqdn="www.atomicdroplet.com")
    logging.info("-----Finished")

Gives::

    1207165538.478 INFO     Connecting to: tiny.20ft.nz
    1207165538.584 INFO     Location has sent resource offer
    1207165538.584 INFO     Ensuring layers are uploaded for: 337c501c333c
    1207165538.736 INFO     No layers need uploading for: 337c501c333c
    1207165538.736 INFO     -----Starting
    1207165538.787 INFO     Spawning container: z8JprcSwZd5wt8k8jSKqFE
    1207165538.837 INFO     Spawning container: aSXB2RpMcA2sihyRzvf2cj
    1207165538.900 INFO     Spawning container: EqSNk64z2WBUiWpjMCKtA7
    ....
    1207165541.372 INFO     Container is running: fs5SCYGpqE6prAtfGwj6w3
    1207165541.900 INFO     Container is running: diosgkCANemzCV4GcPjsz4
    1207165542.148 INFO     Container is running: UyxWTxCx6jRBdHJwbMA2q8
    1207165542.736 INFO     Container is running: VAkyf9jZNZv7Fk6nrphGci
    ....
    1207165555.126 INFO     Connected onto: http://www.atomicdroplet.com:6052/
    1207165555.126 INFO     Waiting on http 200: GUQxBDh9WyCpmBt3xktit2
    1207165555.132 INFO     Created tunnel object onto: GUQxBDh9WyCpmBt3xktit2 (1448 -> 80)
    1207165556.523 INFO     Connected onto: http://www.atomicdroplet.com:1448/
    1207165556.523 INFO     Waiting on http 200: VAkyf9jZNZv7Fk6nrphGci
    1207165556.528 INFO     Created tunnel object onto: VAkyf9jZNZv7Fk6nrphGci (1452 -> 80)
    1207165557.990 INFO     Connected onto: http://www.atomicdroplet.com:1452/
    1207165557.990 INFO     -----Finished

19.25 seconds - one quarter the time. This is also the first time we split spawn into separate ``ensure_image_uploaded`` and ``spawn`` calls since ensuring the upload only needs to happen once.

Obviously this is a somewhat contrived example but the lesson is simple: If you can start containers ahead of when you need them, you will enjoy a (very) significant performance boost.
