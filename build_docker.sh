#!/usr/bin/env bash

# create a pip-installable component then install it and make the docker image
python3 setup.py sdist
docker build --squash -t tfnz/tf .

# clean up
rm -rf dist/
rm -rf tfnz.egg-info/
