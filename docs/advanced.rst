=================
Advanced Spawning
=================

While initially it seems sufficient to merely boot a container, this becomes a limiting factor reasonably quickly. 20ft has support for pre-boot configuration; a 'reboot and reset' that's particularly useful for unit testing; and concurrently booting large numbers of containers.

Pre-boot files
==============

In reality it's rare that a single configuration, baked into the container image during ``docker build``, is going to be suitable for all situations. A database server will need different user configuration; a load balancer needs to be told *what* to load balance; a container under test needs to be passed fixtures and so on. The 'traditional' Docker way of doing this is to write a script that gets started in lieu of the desired process start, is passed various parameters in environment variables and is expected to render any configuration changes within the container itself before starting the desired process. They're nasty to write; worse to debug; and quickly become informal (ie undocumented) interfaces onto the underlying functionality.

Thankfully there's a better way to effect a dynamic configuration and that's by using pre-boot files. These are just text files that are passed as part of the ``spawn_container`` call and are written into the container immediately prior to boot. Here is a simple implementation...::

    import signal
    from tfnz.location import Location

    location = Location()
    preboot = [('/usr/share/nginx/html/index.html', 'Hello World!')]
    container = location.ranked_nodes()[0].spawn_container('nginx', pre_boot_files=preboot)
    container.attach_browser()
    signal.pause()

Obviously this can be extended out to rendering /etc files; and you are able to debug these renders client side and in Python (instead of bash). Preboot files also make an excellent basis for higher level components i.e. a single 'LoadBalancer' class that uses pre-boot files as it's implementation.

Rebooting
=========

It's also possible to reboot a running container, either with or without resetting the contents of the container to it's "as booted" state. This is as simple as calling "reboot" on the container::

    from tfnz.location import Location

    node = Location().ranked_nodes()[0]
    container = node.spawn_container('nginx')
    container.put("/usr/new/path", b'Some data')
    print(container.fetch("/usr/new/path"), flush=True)

    container.reboot()
    print(container.fetch("/usr/new/path"), flush=True)

    container.reboot(reset_filesystem=True)
    try:
        container.fetch("/usr/new/path")
    except ValueError:
        pass

Note that any processes launched in the container will be terminated as part of the reboot.

Concurrent Booting
==================

20ft containers are started asynchronously - that is to say that the actions of asking a container to start and the container having started are, from the perspective of the user, decoupled. As with all things this is obvious given an example:

The image used in these examples is a fairly heavy Apache/Mezzanine/Django/Postgres stack with non-trivial startup costs. Consider the synchronous case::

    import logging
    from tfnz.location import Location

    location = Location()
    location.ensure_image_uploaded('337c501c333c')
    logging.info("-----Starting")
    for n in range(0, 10):
        container = location.ranked_nodes()[0].spawn_container('337c501c333c', no_image_check=True)
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

76.9 seconds. Asynchronously::

    import logging
    from tfnz.location import Location

    location = Location()
    location.ensure_image_uploaded('337c501c333c')
    containers = []
    logging.info("-----Starting")
    for n in range(0, 10):
        container = location.ranked_nodes()[0].spawn('337c501c333c', no_image_check=True)
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

19.25 seconds - one quarter the time. This is also the first time we split spawn into separate ``ensure_image_uploaded`` and ``spawn_container`` calls hence ensuring the upload check only needs to happen once.

Obviously this is a somewhat contrived example but the lesson is simple: If you can start containers ahead of when you need them, you will enjoy a (very) significant performance boost.
