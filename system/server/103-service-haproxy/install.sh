#
### HAPROXY SERVER ###
#

# packages installation
GISLAB_SERVER_INSTALL_PACKAGES="
  haproxy
"
apt-get --assume-yes --force-yes --no-install-recommends install $GISLAB_SERVER_INSTALL_PACKAGES

if [ ! -f /var/lib/gislab/installation.done ]; then
	sed -i 's/^ENABLED=.*/ENABLED=1/' /etc/default/haproxy
fi

cat << EOL > /etc/haproxy/haproxy.cfg
global
#   log 127.0.0.1 local0 warning
    maxconn 2000
    user haproxy
    group haproxy

defaults
    log global
    mode http
    option httplog
    option dontlognull
    option redispatch
    retries 3
    maxconn 2000
    timeout connect 5000
    timeout client 50000
    timeout server 50000

listen mapserver 0.0.0.0:90
    mode http
    stats enable
    stats hide-version
    stats uri /haproxy?stats
    stats refresh 3s
    option httpchk GET /cgi-bin/qgis_mapserv.fcgi?REQUEST=GetCapabilities
    balance static-rr
    fullconn 150
    maxconn 1000
    default-server error-limit 1 on-error fail-check fall 1 inter 10s fastinter 5s downinter 120s rise 2 maxconn 100 maxqueue 25 minconn 25 weight 128
    server localhost 127.0.0.1:91 maxconn 0
EOL

for i in $(seq 50 149); do
        echo "    server client-$i $GISLAB_NETWORK.$i:91 id $i check observe layer7" >> /etc/haproxy/haproxy.cfg
done

service haproxy restart
