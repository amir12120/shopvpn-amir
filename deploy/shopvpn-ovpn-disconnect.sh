#!/bin/sh
PATH=/usr/sbin:/usr/bin:/sbin:/bin
dir=/var/lib/shopvpn-ovpn-events
umask 077
tmp=$(mktemp "${dir}/.XXXXXXXX") || exit 0
printf '%s %s %s\n' "${common_name}" "${bytes_received:-0}" "${bytes_sent:-0}" > "${tmp}"
mv "${tmp}" "${tmp}.evt"
exit 0
