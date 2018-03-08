==========================
Building Apps with the SDK
==========================

As we saw from :ref:`the external architecture <external_architecture>` there needs to be a client program running in order to create a 20ft service. This chapter is about building and deploying these applications. Bear in mind they need to be run from a machine that has Python 3 and ``pip3 install tfnz``, or use the `ready made AMI <https://ap-southeast-2.console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#LaunchInstanceWizard:ami=ami-e1519583>`_ (runs fine on t2.nano, login with alpine@) that has this already set up for you.

Don't forget to login and paste your access keys from ``tfacctbak``.

The Quick Way
=============

A single container app can be deployed extremely quickly:

Run ``nohup tf image &`` to spawn a container from the image - this process will keep running even when you've logged out.

The CLI Tools are SDK Based
===========================

The cli tools - tfnz, tfvolumes etc. etc. - are all merely python applications written around the 20ft SDK. Better still, they are all BSD licensed `open source <https://github.com/20ft/20ft/blob/master/tfnz/cli/tfnz.py>`_ so they can be used as reference material or a starting point for your own applications.


