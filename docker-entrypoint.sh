#!/bin/sh
set -e
chown mcpssh:mcpssh /data
exec gosu mcpssh "$@"
