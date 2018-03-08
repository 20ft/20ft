================
About Containers
================

Containers are basically virtual machines with low startup times and efficient resource usage. They almost all run on the x86-64 Linux ABI and are made with a Linux distribution as their base layer but are very rarely actually *booted*. They have access to a fast non-routable lan, a default route, some form of software defined storage, and in 20ft's case a web gateway. They are usually dedicated to a single task or a particular piece of software.

**Containers are transient** - that is to say that the contents of their filesystems are lost when they restart. The combination of a transient nature and low startup times implies that containers have much shorter lifecycles than traditional servers, being expected to fail entirely and be respawned rather than to report their failure to an administrator and require manual intervention. The short lifecycles and resource efficiency also mean that containers can be deployed for short term tasks - for example to encode a single stream of video, serve a single client, or even conduct a single transaction in an isolated environment.

Five Basic Tasks
================

There are five basic tasks any container infrastructure has to be able to perform:

* Start and stop containers.
* Change the environment in which they start.
* Connect containers to each other.
* Map persistent volumes into the container's file system.
* Allow the outside world to access the containers.

Traditionally this is achieved with a number of services and an *orchestrator*. These are given a description of container images, environments, connections, volumes and port mappings - and will then endeavour to keep the running state identical to this static description.

Unsolved Questions
==================

On the surface this sounds wonderful but leaves us with a number of unsolved questions, for instance:

* How can I customise the /etc files before boot?
* How do I create, store and distribute secrets (passwords, encryptions keys) securely?
* How do I specify scripts for startup and fail events?
* How can I spawn additional processes within the container?
* How can I firewall containers?
* How do create a container from within the application itself?
* How can I put and fetch files onto the container's file system?
* How do I reboot the container without changing it's IP?

The customisation requires writing a startup script, and debugging it, while it's in a container. It's difficult and frustrating work. Distributing secrets is traditionally done through environment variables, which are frequently included in logs so this is not a good idea either. Scripts for events can't be done, and creating a container from within the application involves deliberately creating a giant security problem first.

20ft is about Solving These Problems
====================================

20ft removes the orchestrator and places control back in the hands of the programmer.

**20ft is about writing tiny Python applications against a container SDK** and having these applications handle the questions above...

* Exposing all five of the 'basic tasks' to software.
* Customising /etc files and distributing secrets by passing pre-boot files to the container object's constructor.
* Catching events with simple callback functions or lambdas.
* Calling 'run' or 'spawn' on containers to run additional processes.
* Calling 'put' and 'fetch' on containers for file handling.
* Calling 'reboot' on a container to reboot it.
* Calling 'allow_connection_from' on a container to create a firewall rule.

..  note::
    These applications run identically on a development machine, VPS, or hardware server. 20ft has built in support for running the applications as systemd units (on a server to which you have ssh access), and hence these applications can be treated exactly the same as other linux services.
