#!/usr/local/bin/python3.5
# Copyright (c) 2017 David Preece, All rights reserved.
# 
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted.
# 
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import sys
import os.path
from messidge import default_location, KeyPair

bash_template = """echo 'mkdir -p ~/.20ft
cat > ~/.20ft/%s << EOF
%s
EOF
cat > ~/.20ft/%s.pub << EOF
%s
EOF
cat > ~/.20ft/%s.spub << EOF
%s
EOF
cat > ~/.20ft/default_location << EOF
%s
EOF

chmod 400 ~/.20ft/%s*' | /bin/sh
"""


def main():
    loc = default_location(prefix="~/.20ft") if len(sys.argv) == 1 else sys.argv[1]
    kp = KeyPair(loc, prefix="~/.20ft")
    with open(os.path.expanduser('~/.20ft/%s.spub' % loc)) as f:
        spub = f.read()
    print(bash_template % (loc, kp.secret.decode(), loc, kp.public.decode(), loc, spub, loc, loc))


if __name__ == "__main__":
    main()
