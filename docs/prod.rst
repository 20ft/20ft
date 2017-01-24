=======================
Deploying to Production
=======================

Currently 20ft is designed as a pure compute resource and hence has no explicit support for public Internet connectivity or persistent datasets. The best way to create a server using 20ft is to:

* Create a VM on a public Internet provider (or an intranet). The VM will require little compute power so a small instance will work well.
* Use a process manager to...
* Run ``tf -v --bind aa.bb.cc.dd --offset n image`` where 'bind' is onto your Internet IP (or an IP within a virtual rack) to run the container and create tunnels onto its exposed ports.

The offset is optional and maps (for example) container port 80 to local port 8080 (with an offset of 8000). This is purely so tf does not need to be run as root. This technique works equally well for Intranets or the public Internet. For the public Internet is recommended that web servers ve run behind a proxy or source protecting CDN such as `Cloudflare <https://cloudflare.com/>`_ or `Fastly <https://fastly.com/>`_ (both of which provide low volume accounts free of charge).

The ability to directly bind exposed ports onto an Internet addressable IP will be available soon.
