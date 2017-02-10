=======================
Deploying to Production
=======================

Currently 20ft is designed as a pure compute resource and hence has no explicit support for public Internet connectivity or persistent datasets. This will change in a future revision of the SDK.

The Quick Way
=============

A single container app can be deployed extremely quickly:

* Create a VM with the 20ft SDK (and your account keys) on a public Internet provider (or an intranet). The `quickstart AMI <https://ap-southeast-2.console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#LaunchInstanceWizard:ami=ami-b0a5a3d3>`_ is a good candidate.
* Run ``sudo nohup tf --public image &`` to spawn a container from the image and create tunnels onto its exposed ports.

This process will keep running even when you've logged out.

For the public Internet is recommended that web servers are run behind a proxy or source protecting CDN such as `Cloudflare <https://cloudflare.com/>`_ or `Fastly <https://fastly.com/>`_ (both of which provide low volume accounts free of charge); and that tf is run as a non-root user using port numbers greater than 1024. See ``man tf`` for more details.

The Better Way
==============

Rather more 'in the intention of' 20ft is to create a tiny Python program and either run that or proxy onto it. The function 'get_external_ip' used so we can bind the tunnel onto the external IP address::

    import signal
    from tfnz.location import Location
    from tfnz import get_external_ip

    container = Location().best_node().spawn('nginx')
    container.attach_tunnel(80, localport=8080, bind=get_external_ip())
    signal.pause()

Note that 'get_external_ip' finds the external IP for the VM and that (particularly in the case of AWS) the Internet routable IP may be different.

From here on it's a question of using your favourite process manager. Note that it's important the service runs as the user you were logged in as when you installed your 20ft keys - the Location object looks for the keys in ~/.20ft so if the process is running as root it will look in /root/.20ft where they are probably not installed.

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

Also notable is the resource usage - 17MB for the above example so this technique can be used to 'proxy' containers running on powerful hardware into IoT devices or similarly constrained environments.

The construction of more complex services is covered in the next chapter...
