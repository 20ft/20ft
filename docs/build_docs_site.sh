#!/usr/bin/env bash
# sphinx
export PYTHONPATH=".."
make html
cp _build/html/_static/fonts/fontawesome-webfont.woff _build/html/_static/fonts/fontawesome-webfont.woff2

# man pages
# https://github.com/bagder/roffit
apps=(tfnz tfvolumes tfdomains tfacctbak tfresources tfcache tfdescribe tflocations)
for app in ${apps[*]}; do
    ~/roffit/roffit ../$app.1 > _build/html/$app.html
done

# dockerise
docker build -t tfnz/docs .
