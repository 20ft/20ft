==============================
Developing Client Applications
==============================

It would make sense to start, again, with the canonical nginx 'hello world' app. ::

    from tfnz import *

    loc = location.Location()
    node = loc.node()
    ctr = node.spawn_container('nginx')
    ctr.attach_tunnel(80, localport=8080)
    loc.run()

Unsurprisingly this is the same code that we ran :ref:`when using the SDK live <live_running>` with the exception of ``loc.run()``. This blocks waiting for the background message thread to complete (or throw an exception). Without it the application would exit, removing the container at the same time.

Garbage Collection
==================

When the connection with the location finishes (either by calling disconnect, handled automatically in ``Location.run`` or by being killed), 20ft will garbage collect any resources that were allocated. This includes containers, tunnels, web endpoints, but *not* persistent volumes.

The connection will also be judged to be closed if it fails for (at minimum) two minutes.

Tagging and Discovery
=====================

It is often desirable to be able to separate concepts from specific instantiations. For example: a database container attaches to a volume. We could pass the ID of the volume to the container (naming a specific instantiation), but it would be easier to pass the concept "database_volume" and to have that automatically resolved to a specific instance. 20ft achieves this through tagging.

A 20ft object that is `taggable <ref.html#tfnz.Taggable>`_ (currently persistent volumes and containers) is held in a `tagged collection <ref.html#tfnz.TaggedCollection>`_. Retrieving a tagged object is by calling ``TaggedCollection.get``, passing the user PK and a string that is either: the object uuid, the object tag, or a 'uuid:tag' pair where this pair can also be created by calling ``Taggable.display_name``.

This works for objects inside a single 20ft location. To resolve externally (i.e. for a microservice) create a web endpoint with an appropriate subdomain name.

Connecting to Locations
=======================

Thus far we have only ever called the constructor for ``Location`` without examining its construction time options. These fall into three broad categories:

* You can select a non-default location to connect to (location=) and a non-dns ip to use when connecting (location_ip=)
* You can select either no additional logging configuration (quiet=) or verbose logging (debug=)
* Finally you can set a method to be called back when a new node is instantiated (new_node_callback=)

There is nothing preventing you from connecting to more than one location, or any single location more than once (should you need isolated sessions, for example). Note that while the appearance of a new node causes an event, a disappearance does not. This is the desired behaviour because the closure of each container running on the node *is* reported and the node is marked as having no spare capacity (and hence won't be chosen to respawn the container).

Incidentally, minor network disconnections are recovered transparently.

**Resource Offers**

When we first connect to a location, the location returns a list of resources that we may use - nodes, volumes, external containers, and web endpoints. The framework keeps these resources up to date in real time (except for the endpoints which are basically static anyway). The resource offer for a particular location is encapsulated as part of the ``Location`` object itself and can be accessed with ``Location.nodes``, ``Location.volumes``, ``Location.externals``, ``Location.tunnels`` and ``Location.endpoints``. Volumes and externals are held in a taggable collection and hence can be fetched with their tag.

**Images**

The location holds a cache of both image descriptions, and the layers used to create the final images. The descriptions are namespaced on a per-user basis although the layers themselves are not. It is possible to explicitly ensure a given image is available using ``Location.ensure_image_uploaded`` and this is the mechanism by which ``tfcache`` works, although it is also implied by merely running a container.

Volumes
=======



Choosing Nodes
==============

TBD: ranked, updates

Parent creates and destroys child objects

Spawning Containers
===================

TBD - command, entrypoint debate, asleep/awake, various forms of waiting

stdin

Pre-boot Configuration
======================

TBD

Using Callbacks
===============

termination, stdout - similar, differences

Rebooting Containers
====================

In-place, restore snapshot

Fetch/Put Files
===============

TBD

Running Processes
=================

TBD: sync, async, shell

Creating Tunnels
================

TBD: Tunnels, SSH

Clusters and Endpoints
======================

TBD: load balance, ssl, clusters, single user. Not raw IP.

Connecting Containers
=====================

TBD: allow, disallow

External Containers
===================

TBD

Microservices
=============

TBD



