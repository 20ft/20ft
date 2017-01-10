#!/bin/bash
if [ "$#" -ne 1 ]; then
    echo "Usage: tfnz-repl.sh location"
    exit 0
fi
python3 -i -c "import tfnz.location; loc=tfnz.location.Location(\"$1\"); node=loc.best_node(); tfnz.location.intro()"
