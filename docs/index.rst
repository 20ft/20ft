===============
The 20ft.nz SDK
===============

Conventional container platforms require that you interact with an orchestrator - Kubertenes, Marathon, Nomad etc. They all attempt to build a statically described platform and with little or no support for ordering, custom test scripts, static networking or location awareness.

20ft is a dynamic platform with an Object Oriented SDK - you write orchestration instructions in the same way you write other software. It's simpler, makes no assumptions about what you are trying to achieve and retains compatibility with Docker. The platform garbage collects on disconnection so don't worry about leaking containers, tunnels, addresses or otherwise - it's all taken care of.

Contents
========

..  toctree::

    quick
    sdk
    advanced
    prod
    examples
    ref
