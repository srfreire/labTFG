#!/bin/sh
set -e

# Resolve the nameservers nginx should use at request time so that
# Railway's *.railway.internal hostnames can be looked up after start.
# nginx needs IPv6 nameservers wrapped in square brackets, otherwise it
# misreads the final ":<hex>" segment as a port.
NGINX_LOCAL_RESOLVERS=$(awk '
  $1=="nameserver" {
    if (index($2, ":") > 0) { print "[" $2 "]" } else { print $2 }
  }
' /etc/resolv.conf | tr '\n' ' ')
NGINX_LOCAL_RESOLVERS=$(printf '%s' "$NGINX_LOCAL_RESOLVERS" | sed 's/[[:space:]]*$//')
if [ -z "$NGINX_LOCAL_RESOLVERS" ]; then
  NGINX_LOCAL_RESOLVERS="1.1.1.1 8.8.8.8"
fi
export NGINX_LOCAL_RESOLVERS

echo "nginx local resolvers: $NGINX_LOCAL_RESOLVERS"

# Hand off to the stock nginx entrypoint, which runs envsubst on
# /etc/nginx/templates/*.template before starting the daemon.
exec /docker-entrypoint.sh "$@"
