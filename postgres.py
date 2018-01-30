from tfnz.location import Location
from tfnz.components.postgresql import Postgresql
from signal import pause

loc = Location()

try:
    vol = loc.volume('postgresql_test')
except KeyError:
    vol = loc.create_volume('postgresql_test')

try:
    postgresql = Postgresql.spawn(loc, vol, log_callback=lambda o, d: print(d.decode()))
    postgresql.create_ssh_server()
    pause()
except:
    loc.disconnect()
