=======================
Deploying to Production
=======================

20ft is designed as a pure compute resource and hence has no explicit support for public Internet connectivity. The intention is that for deployment a lightweight proxy be deployed via a VPS provider (or similar) in a convenient location. Note that sydney.20ft.nz is approx 1.5ms ping from AWS Sydney.

The Quick Way
=============

A single container app can be deployed extremely quickly:

* Create a VM with the 20ft SDK (and your account keys). The `quickstart AMI <https://ap-southeast-2.console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#LaunchInstanceWizard:ami=ami-b0a5a3d3>`_ is a good candidate.
* Run ``sudo nohup tf image &`` to spawn a container from the image and create tunnels onto its exposed ports.

This process will keep running even when you've logged out.

Running without sudo is also possible if local port numbers > 1024 are specified. To achieve this use the `--offset` flag when running `tf`. For instance `nohup tf --offset 8000 image &`` run with an image that exposes port 80 will create a local proxy on port 8080.

For the public Internet is recommended that web servers are run behind a proxy or source protecting CDN such as `Cloudflare <https://cloudflare.com/>`_ or `Fastly <https://fastly.com/>`_ (both of which provide low volume accounts free of charge); and that tf is run as a non-root user. See ``man tf`` for more details.

The Better Way
==============

Rather more 'in the intention of' 20ft is to create a tiny Python program and either run that or proxy onto it... ::

    import signal
    from tfnz.location import Location

    container = Location().best_node().spawn('nginx')
    container.attach_tunnel(80, localport=8080)
    signal.pause()

From here on it's a question of using your favourite process manager. Note that it's important the service runs as the user you were logged in as when you installed your 20ft keys - the Location object looks for the keys in ~/.20ft so if the process is running as root it will look in /root/.20ft where they are probably not installed. Moving the directory from ~/.20ft to ~someuser/.20ft will work but you need to `chown -R someuser ~someuser/.20ft` the files as well.

Here is a systemd configuration that will work on the quickstart AMI: ::

    [Unit]
    Description=Example service written with 20ft

    [Service]
    ExecStart=/usr/bin/python3 /home/ubuntu/tf-server.py
    User=ubuntu
    Restart=always

If that is saved as /etc/systemd/user/tf-server.service (as root), then use:

* ``sudo systemctl enable /etc/systemd/user/tf-server.service`` to install it, and
* ``sudo systemctl start tf-server.service`` to start the server.
* You can check this with ``systemctl status tf-server`` and if this doesn't get the result we want,
* use ``journalctl -n 50`` to see why.

Now we are part of systemd the server will restart if the system reboots; restart the process if it crashes or has a problem; log to the journal and generally be a good citizen.

Also notable is the resource usage - 17MB for the above example so this technique can be used to proxy containers running on powerful hardware into IoT devices or similarly constrained environments.

The Best Way
============

In reality we are going to want to need (at least) development and production environments. These can run simultaneously and in the same location with the same account, but we still need to be able to differentiate between the two for volume mounting and connection to a proxy, load balancer or other non-container infrastructure. Here is one (marginally pseudocode) possible solution...  ::

    #!/usr/local/bin/python3
    import signal
    import logging
    import argparse
    from tfnz.location import Location

    parser = argparse.ArgumentParser(prog='our-tf-service')
    parser.add_argument('--prod', action='store_true', help="Run as production environment")
    parser.add_argument('image', help="Image to use as webapp")
    args = parser.parse_args()
    loc = Location(debug_log=not args.prod)

    # Fetch or create the database volume
    dbname = 'prod/db' if args.prod else 'dev/db'
    try:
        volume_uuid = loc.kv[dbname]
        node, vol = loc.node_and_volume(volume_uuid)
    except KeyError:
        node = loc.best_node()
        vol = node.create_volume()
        loc.set_kv({dbname: vol.uuid})

    logging.info("Starting our-tf-service " +
                 ("ON THE PRODUCTION ENVIRONMENT." if args.prod else
                  "on the development environment."))
    logging.info("Using webserver image: " + args.image)

    db = node.spawn_container("postgres", volumes=[(vol, '/db')])
    app = node.spawn_container(args.image,
                               pre_boot_files=[('/etc/webapp.cfg', 'db=' + db.ip)])
    db.allow_connection_from(app)
    signal.pause()

This can now be launched with ``our-tf-service dev1mageuu1d`` during development or ``our-tf-service --prod prod1mageuu1d`` for deployment.
Deploying a new image for the app is as simple as changing the image uuid. The systemd configuration outlined above can, obviously, be modified to suit.

Snapshots and Rollbacks
=======================

Because the containers and persistent volumes are based on ZFS volumes we have lightweight (i.e. fast) snapshot/rollback. For 20ft this has been simplified down to a single snapshot point...::

    from tfnz.location import Location

    node = Location().best_node()
    volume = node.create_volume()
    container = node.spawn_container('nginx', volumes=[(volume, '/mount/point')])

    container.put('/mount/point/test', b'I am a test')
    volume.snapshot()
    container.put('/mount/point/test', b'I am a carrot')
    print(container.fetch('/mount/point/test'))
    volume.rollback()
    print(container.fetch('/mount/point/test'))

    node.destroy_volume(volume)

Similarly it is possible to reboot a container with its image restored to the "as shipped" state. This is particularly useful for unit testing. ::

    from tfnz.location import Location


    node = Location().best_node()
    ctr = node.spawn_container('nginx')
    ctr.put('/usr/share/nginx/html/index.html', b'A big mess from a unit test')
    assert ctr.fetch('/usr/share/nginx/html/index.html') == b'A big mess from a unit test'
    ctr.reboot(reset_filesystem=True)
    assert b'nginx' in ctr.fetch('/usr/share/nginx/html/index.html')
